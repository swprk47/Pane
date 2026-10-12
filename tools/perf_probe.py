"""
Playback performance probe: CPU, GPU (per engine), memory, dropped frames, displayed
FPS, render time and GUI-thread latency while Pane plays real clips.

    python tools/perf_probe.py CLIP [CLIP ...] [--seconds 10] [--modes windowed,fullscreen]
                               [--hwdec auto-copy|no|d3d11va] [--label text]

Every (clip, mode) pair runs in a fresh window: warm up, then measure. The Pane window
is moved/resized and the mouse is left alone; keep other heavy programs closed for
meaningful numbers.

GPU usage comes from the Windows "GPU Engine" performance counters of this process
(via typeperf), summed per engine type: 3D, VideoDecode, VideoProcessing, Copy, ...
"""
import argparse
import csv
import ctypes
import io
import os
import re
import statistics
import subprocess
import sys
import time
from ctypes import wintypes
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

kernel32 = ctypes.windll.kernel32
psapi = ctypes.windll.psapi
user32 = ctypes.windll.user32
kernel32.GetCurrentProcess.restype = ctypes.c_void_p


class FILETIME(ctypes.Structure):
    _fields_ = [("lo", wintypes.DWORD), ("hi", wintypes.DWORD)]

    def seconds(self):
        return ((self.hi << 32) | self.lo) / 1e7


def process_cpu_seconds() -> float:
    c, e, k, u = FILETIME(), FILETIME(), FILETIME(), FILETIME()
    kernel32.GetProcessTimes(ctypes.c_void_p(kernel32.GetCurrentProcess()), ctypes.byref(c), ctypes.byref(e),
                             ctypes.byref(k), ctypes.byref(u))
    return k.seconds() + u.seconds()


class PMC(ctypes.Structure):
    _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD), ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t), ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t), ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t), ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t)]


def working_set_mb() -> float:
    pmc = PMC()
    pmc.cb = ctypes.sizeof(pmc)
    psapi.GetProcessMemoryInfo(ctypes.c_void_p(kernel32.GetCurrentProcess()), ctypes.byref(pmc), pmc.cb)
    return pmc.WorkingSetSize / 1048576


def start_gpu_counter(seconds: int):
    """typeperf sampling this process's GPU engines once a second."""
    counter = rf"\GPU Engine(pid_{os.getpid()}_*)\Utilization Percentage"
    return subprocess.Popen(["typeperf", counter, "-si", "1", "-sc", str(seconds)],
                            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, encoding="utf-8", errors="replace")


def parse_gpu(output: str) -> dict:
    """-> {engine type: mean over samples of the summed utilization across its instances}"""
    rows = list(csv.reader(io.StringIO(output)))
    rows = [r for r in rows if r and not r[0].startswith("Exiting") and r[0] != ""]
    if len(rows) < 2:
        return {}
    header, data = rows[0], rows[1:]
    engines = [(m.group(1) if (m := re.search(r"engtype_([A-Za-z0-9]+)", h)) else None) for h in header]
    per_type = {}
    for row in data:
        sums = {}
        for eng, cell in zip(engines[1:], row[1:]):
            if eng is None:
                continue
            try:
                sums[eng] = sums.get(eng, 0.0) + float(cell)
            except ValueError:
                pass
        for eng, v in sums.items():
            per_type.setdefault(eng, []).append(v)
    return {eng: statistics.mean(vals) for eng, vals in per_type.items()}


def percentile(values, p):
    if not values:
        return 0.0
    values = sorted(values)
    return values[min(len(values) - 1, int(len(values) * p))]


def measure(clip: str, mode: str, seconds: int, hwdec: str, opaque: bool = False):
    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import QTimer
    from ui.main_window import MainWindow
    from ui.mpv_gl import MpvGLWidget

    app = QApplication.instance() or QApplication(sys.argv)

    paints = []                                   # (start, duration)
    orig_paint = MpvGLWidget.paintGL

    def timed_paint(self):
        t0 = time.perf_counter()
        orig_paint(self)
        paints.append((t0, time.perf_counter() - t0))

    MpvGLWidget.paintGL = timed_paint
    w = MainWindow()                         # (the window has no acrylic backdrop any more)
    if opaque:
        pass                                 # experiment below: an ordinary opaque window, no translucency
    if opaque:
        from PySide6.QtCore import Qt
        w.setAttribute(Qt.WA_TranslucentBackground, False)
    try:
        w.show()
        w.resize(1000, 600)
        w.move(100, 100)
        user32.SetWindowPos(int(w.winId()), -1, 0, 0, 0, 0, 0x43)
        if hwdec != "auto-copy":
            w.engine.mpv.hwdec = hwdec

        lag = []                                  # GUI-thread latency of a 10 ms timer
        last = [time.perf_counter()]

        def tick():
            now = time.perf_counter()
            lag.append(max(0.0, (now - last[0]) * 1000 - 10))
            last[0] = now

        timer = QTimer()
        timer.setInterval(10)
        timer.timeout.connect(tick)

        def pump(sec):
            end = time.time() + sec
            while time.time() < end:
                app.processEvents()
                time.sleep(0.002)

        w.load_media_file(clip)
        w.engine.mpv.loop_file = "inf"
        pump(1.0)
        if mode == "fullscreen":
            w.toggle_fullscreen()
        pump(2.5)                                 # warm-up (shaders, decoder queue, window animation)

        def info(key):
            return w.engine.get_media_info().get(key)

        # measure for at most `seconds`, but never run into the clip's loop point
        duration = info("duration") or seconds
        seconds = max(3, min(seconds, int(duration - 4.5)))
        gpu_proc = start_gpu_counter(seconds)
        drops0 = (info("dropped_vo") or 0, info("dropped_decoder") or 0)
        p_start, t_start = len(paints), time.perf_counter()
        cpu0, mem_samples = process_cpu_seconds(), []
        fps_samples = []
        last[0] = time.perf_counter()               # restart the reference: the first tick must not include setup time
        timer.start()
        end = time.time() + seconds
        while time.time() < end:
            pump(1.0)
            mem_samples.append(working_set_mb())
            fps_samples.append(info("actual_fps") or 0)
        timer.stop()
        wall = time.perf_counter() - t_start
        cpu = process_cpu_seconds() - cpu0
        drops1 = (info("dropped_vo") or 0, info("dropped_decoder") or 0)
        decoder = info("hwdec")
        vw, vh, vfps = info("width"), info("height"), info("container_fps")

        try:
            out, _ = gpu_proc.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            gpu_proc.kill()
            out, _ = gpu_proc.communicate()
        gpu = parse_gpu(out)

        sp = [(t, d) for t, d in paints[p_start:] if t >= t_start]
        gaps = [(b[0] - a[0]) * 1000 for a, b in zip(sp, sp[1:])]
        return {
            "clip": os.path.basename(clip), "mode": mode, "hwdec_option": hwdec, "decoder": decoder or "no",
            "res": f"{vw}x{vh}", "video_fps": vfps,
            "cpu_core_pct": cpu / wall * 100, "cpu_total_pct": cpu / wall / (os.cpu_count() or 1) * 100,
            "mem_mb": statistics.mean(mem_samples) if mem_samples else 0,
            "gpu": gpu,
            "drop_vo": drops1[0] - drops0[0], "drop_dec": drops1[1] - drops0[1],
            "shown_fps": len(sp) / wall, "mpv_fps": statistics.mean(fps_samples) if fps_samples else 0,
            "gap_mean": statistics.mean(gaps) if gaps else 0, "gap_p99": percentile(gaps, 0.99), "gap_max": max(gaps, default=0),
            "render_mean": statistics.mean(d * 1000 for _t, d in sp) if sp else 0,
            "render_max": max((d * 1000 for _t, d in sp), default=0),
            "lag_p95": percentile(lag, 0.95), "lag_max": max(lag, default=0),
            "seconds": wall,
        }
    finally:
        MpvGLWidget.paintGL = orig_paint
        w.close()
        app.processEvents()


def fmt_gpu(gpu: dict, key: str) -> str:
    return f"{gpu.get(key, 0):4.0f}%"


def report(results, label):
    print("\n" + "=" * 118)
    print(f"성능 측정 {('- ' + label) if label else ''}  (CPU 코어 수 {os.cpu_count()}; CPU%는 코어 1개를 100%로 본 값 / 괄호는 전체 대비)")
    print("=" * 118)
    head = (f"{'영상':26s}{'모드':11s}{'디코더':14s}{'CPU':>14s}{'GPU 3D':>8s}{'디코드':>8s}{'비디오처리':>10s}{'복사':>7s}"
            f"{'메모리':>9s}{'버린프레임':>11s}{'표시FPS':>9s}")
    print(head)
    for r in results:
        g = r["gpu"]
        print(f"{r['clip'][:25]:26s}{r['mode']:11s}{r['decoder'][:13]:14s}"
              f"{r['cpu_core_pct']:6.0f}% ({r['cpu_total_pct']:3.0f}%)"
              f"{fmt_gpu(g, '3D'):>8s}{fmt_gpu(g, 'VideoDecode'):>8s}{fmt_gpu(g, 'VideoProcessing'):>10s}{fmt_gpu(g, 'Copy'):>7s}"
              f"{r['mem_mb']:7.0f}MB{r['drop_vo']:>5d}+{r['drop_dec']:<5d}"
              f"{r['shown_fps']:6.1f}/{r['video_fps'] or 0:<4.0f}")
    print("-" * 118)
    print(f"{'영상':26s}{'모드':11s}{'그리기 간격 평균/p99/최대(ms)':>34s}{'렌더 평균/최대(ms)':>22s}{'UI 지연 p95/최대(ms)':>24s}")
    for r in results:
        print(f"{r['clip'][:25]:26s}{r['mode']:11s}"
              f"{r['gap_mean']:12.1f} /{r['gap_p99']:6.1f} /{r['gap_max']:6.0f}"
              f"{r['render_mean']:12.1f} /{r['render_max']:6.1f}"
              f"{r['lag_p95']:12.1f} /{r['lag_max']:6.0f}")
    print("=" * 118)
    print("버린프레임 = 출력(VO)+디코더. 표시FPS = 실제로 그려진 횟수/초 / 영상 FPS. UI 지연 = 10ms 타이머가 늦게 도착한 정도(UI 스레드가 막힌 시간).")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("clips", nargs="+")
    ap.add_argument("--seconds", type=int, default=10)
    ap.add_argument("--modes", default="windowed,fullscreen")
    ap.add_argument("--hwdec", default="auto-copy", help="mpv hwdec option for this run (auto-copy, no, d3d11va, ...)")
    ap.add_argument("--label", default="")
    ap.add_argument("--opaque", action="store_true", help="experiment: opaque window without acrylic")
    args = ap.parse_args()

    # keep the probe away from the user's saved settings (resume positions etc.)
    import core.settings as cs
    cs.APP_NAME, cs.LEGACY_APP_NAME = "PanePerf", "PanePerfLegacy"
    from PySide6.QtCore import QSettings
    for group in ("AppSettings", "ControllerLayout", "SpeedSettings"):
        QSettings("PanePerf", group).clear()

    results = []
    for clip in args.clips:
        for mode in args.modes.split(","):
            print(f"[perf] {os.path.basename(clip)} / {mode} / hwdec={args.hwdec} ...", flush=True)
            results.append(measure(clip, mode, args.seconds, args.hwdec, args.opaque))
    report(results, args.label or f"hwdec={args.hwdec}" + (" opaque" if args.opaque else ""))


if __name__ == "__main__":
    main()
