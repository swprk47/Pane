"""
Flicker / dropped-frame probe.

Plays a color-bar test clip and, while scripted UI scenarios run (control fade,
popups, OSD, window move/resize, fullscreen, PIP ...), samples a few fixed
screen pixels of the video from a background thread every ~2 ms. A "blank" is a
moment where those pixels stop showing the expected video colors. It also times
every paintGL call (gap between paints, render duration).

    python tools/flicker_probe.py [--only fade,popups] [--seconds 4] [--block]

It moves the mouse cursor and the window; don't touch the mouse while it runs
and keep the Pane window uncovered. Results are printed per scenario.
"""
import argparse
import ctypes
import os
import statistics
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32
gdi32.GetPixel.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int]
gdi32.GetPixel.restype = ctypes.c_uint
user32.GetDC.restype = ctypes.c_void_p
user32.GetDC.argtypes = [ctypes.c_void_p]
user32.ReleaseDC.argtypes = [ctypes.c_void_p, ctypes.c_void_p]

# the color-bar test clip: left to right red, green, yellow, blue, magenta, cyan
EXPECTED = ((0.08, (255, 0, 0)), (0.25, (0, 255, 0)), (0.42, (255, 255, 0)))
SAMPLE_Y = 0.22          # above the moving diagonal, below the top scrim and timer box
TOLERANCE = 120          # per-point color distance that still counts as "video"
STRIP_X0, STRIP_W, STRIP_Y = 120, 560, 300   # strip mode: inside the video in windowed, PIP and fullscreen


def ensure_clip(seconds=40) -> str:
    """A long color-bar clip in the temp dir (the 3 s sample loops too often)."""
    path = Path(os.environ.get("TEMP", ".")) / f"pane_probe_{seconds}s.mp4"
    if path.exists():
        return str(path)
    os.environ["PATH"] = str(ROOT / "lib" / "mpv") + os.pathsep + os.environ["PATH"]
    os.add_dll_directory(str(ROOT / "lib" / "mpv"))
    import mpv
    print(f"[probe] encoding a {seconds}s test clip ...", flush=True)
    m = mpv.MPV(o=str(path), of="mp4", ovc="libx264", vo="null", ao="null", ytdl=False)
    m.play(f"av://lavfi:testsrc2=duration={seconds}:size=1280x720:rate=30")
    m.wait_for_playback()
    m.terminate()
    return str(path)


class Sampler(threading.Thread):
    """Reads one 1-px screen strip covering the expected-color points as fast as it
    can (a screen read costs ~7 ms regardless of size, so one strip per sample)
    and records runs of "bad" samples."""
    STRIP_MAX = 1400

    def __init__(self):
        super().__init__(daemon=True)
        self.points = None            # [(x, y, rgb)], updated by the GUI thread
        self.mode = "points"          # "points" (follows the window) or "strip" (fixed screen strip)
        self.stop_flag = False
        self.samples = 0
        self.bad_runs = []            # (start_time, duration_s)
        self._run_start = None

    def run(self):
        from ctypes import wintypes

        class BITMAPINFOHEADER(ctypes.Structure):
            _fields_ = [("biSize", wintypes.DWORD), ("biWidth", ctypes.c_long), ("biHeight", ctypes.c_long),
                        ("biPlanes", wintypes.WORD), ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
                        ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", ctypes.c_long),
                        ("biYPelsPerMeter", ctypes.c_long), ("biClrUsed", wintypes.DWORD), ("biClrImportant", wintypes.DWORD)]

        for fn, args, res in (
            (gdi32.CreateCompatibleDC, [ctypes.c_void_p], ctypes.c_void_p),
            (gdi32.CreateCompatibleBitmap, [ctypes.c_void_p, ctypes.c_int, ctypes.c_int], ctypes.c_void_p),
            (gdi32.SelectObject, [ctypes.c_void_p, ctypes.c_void_p], ctypes.c_void_p),
            (gdi32.BitBlt, [ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                            ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_uint], ctypes.c_int),
            (gdi32.GetDIBits, [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint, ctypes.c_uint, ctypes.c_void_p,
                               ctypes.c_void_p, ctypes.c_uint], ctypes.c_int),
        ):
            fn.argtypes, fn.restype = args, res

        hdc = user32.GetDC(None)
        mem = gdi32.CreateCompatibleDC(hdc)
        bmp = gdi32.CreateCompatibleBitmap(hdc, self.STRIP_MAX, 1)
        gdi32.SelectObject(mem, bmp)
        bi = BITMAPINFOHEADER()
        bi.biSize = ctypes.sizeof(bi)
        bi.biWidth, bi.biHeight, bi.biPlanes, bi.biBitCount = self.STRIP_MAX, -1, 1, 32   # top-down 32 bpp
        buf = (ctypes.c_ubyte * (self.STRIP_MAX * 4))()
        try:
            while not self.stop_flag:
                if self.mode == "strip":
                    # Geometry-independent: a fixed screen strip that lies inside the video
                    # for every window size we use. Video present = most pixels are saturated.
                    x0, width, y = STRIP_X0, STRIP_W, STRIP_Y
                    gdi32.BitBlt(mem, 0, 0, width, 1, hdc, x0, y, 0x00CC0020)
                    t = time.perf_counter()
                    gdi32.GetDIBits(mem, bmp, 0, 1, buf, ctypes.byref(bi), 0)
                    sat = 0
                    n = 0
                    for i in range(0, width, 4):
                        b, g, r = buf[i * 4], buf[i * 4 + 1], buf[i * 4 + 2]
                        n += 1
                        if max(r, g, b) - min(r, g, b) > 150:
                            sat += 1
                    bad = 2 if sat / max(1, n) < 0.6 else 0
                else:
                    pts = self.points
                    if not pts:
                        time.sleep(0.005)
                        continue
                    x0 = min(p[0] for p in pts)
                    width = min(self.STRIP_MAX, max(p[0] for p in pts) - x0 + 1)
                    y = pts[0][1]
                    gdi32.BitBlt(mem, 0, 0, width, 1, hdc, x0, y, 0x00CC0020)            # SRCCOPY
                    t = time.perf_counter()
                    gdi32.GetDIBits(mem, bmp, 0, 1, buf, ctypes.byref(bi), 0)
                    bad = 0
                    for x, _y, rgb in pts:
                        off = (x - x0) * 4                                              # BGRA
                        got = (buf[off + 2], buf[off + 1], buf[off])
                        if sum(abs(a - b) for a, b in zip(got, rgb)) > TOLERANCE:
                            bad += 1
                self.samples += 1
                if bad >= 2:
                    if self._run_start is None:
                        self._run_start = t
                elif self._run_start is not None:
                    self.bad_runs.append((self._run_start, t - self._run_start))
                    self._run_start = None
        finally:
            user32.ReleaseDC(None, hdc)


def run(args):
    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import QPoint
    from ui.main_window import MainWindow
    from ui.mpv_gl import MpvGLWidget

    # keep the probe away from the user's real saved settings (resume positions etc.)
    import core.settings as cs
    cs.APP_NAME, cs.LEGACY_APP_NAME = "PaneProbe", "PaneProbeLegacy"
    from PySide6.QtCore import QSettings
    for group in ("AppSettings", "ControllerLayout", "SpeedSettings"):
        QSettings("PaneProbe", group).clear()

    app = QApplication(sys.argv)
    clip = args.clip or ensure_clip()

    # --- paint timing (patched in, no app code changes) ---
    paints = []                                   # (start, duration)
    orig_paint = MpvGLWidget.paintGL

    def timed_paint(self):
        t0 = time.perf_counter()
        orig_paint(self)
        paints.append((t0, time.perf_counter() - t0))

    MpvGLWidget.paintGL = timed_paint

    if args.block:
        MpvGLWidget.BLOCK_FOR_TARGET_TIME = True
        print("[probe] render() WILL block for the target time (the old behaviour)", flush=True)

    w = MainWindow()
    w.show()
    w.resize(1000, 600)
    w.move(100, 100)
    user32.SetWindowPos(int(w.winId()), -1, 0, 0, 0, 0, 0x43)

    sampler = Sampler()

    def pump(sec):
        end = time.time() + sec
        while time.time() < end:
            app.processEvents()
            update_points()
            time.sleep(0.003)

    def update_points():
        vp = w.viewport
        if not vp.isVisible() or vp.width() < 200:
            sampler.points = None
            return
        pts = []
        for fx, rgb in EXPECTED:
            g = vp.mapToGlobal(QPoint(int(vp.width() * fx), int(vp.height() * SAMPLE_Y)))
            pts.append((g.x(), g.y(), rgb))
        sampler.points = pts

    def move_cursor(x, y):
        user32.SetCursorPos(int(x), int(y))

    # ---------------- scenarios ----------------
    def sc_steady(seconds):
        pump(seconds)

    def sc_hidden(seconds):
        move_cursor(5, 5)                                   # away from the window
        w.controller.hold_visible = None
        w.controller._fade_out()
        pump(seconds)

    def sc_paused(seconds):
        w.engine.pause()
        pump(seconds)
        w.engine.play()

    def sc_fade(seconds):
        end = time.time() + seconds
        while time.time() < end:
            w.controller.trigger_activity()
            pump(0.5)
            w.controller.hold_visible = None
            w.controller.volume_popup.hide()
            w.controller._fade_out()
            pump(0.5)

    def sc_mouse(seconds):
        g = w.viewport.mapToGlobal(QPoint(300, 200))
        end = time.time() + seconds
        i = 0
        while time.time() < end:
            move_cursor(g.x() + (i % 40) * 6, g.y() + (i % 25) * 4)
            i += 1
            pump(0.03)

    def sc_popups(seconds):
        end = time.time() + seconds
        while time.time() < end:
            w._show_speed_popup(); pump(0.45)
            w.speed_popup.hide(); pump(0.25)
            w.toggle_media_info(); pump(0.6)
            w.toggle_media_info(); pump(0.25)
            w.controller.volume_popup.open_above(w.controller.btn_mute); pump(0.4)
            w.controller.volume_popup.hide(); pump(0.25)

    def sc_osd(seconds):
        end = time.time() + seconds
        while time.time() < end:
            w.change_speed_relative(+0.05); pump(0.25)
            w.change_speed_relative(-0.05); pump(0.25)
        w.engine.reset_speed()

    def sc_move(seconds):
        end = time.time() + seconds
        x = 100
        while time.time() < end:
            x += 6 if (int((time.time() * 10)) % 40) < 20 else -6
            w.move(x, 100)
            pump(0.016)

    def sc_resize(seconds):
        end = time.time() + seconds
        i = 0
        while time.time() < end:
            i += 1
            w.resize(900 + (i % 30) * 6, 560 + (i % 20) * 3)
            pump(0.03)
        w.resize(1000, 600)

    def sc_menu(seconds):
        """The right-click menu is a separate top-level popup window."""
        from PySide6.QtWidgets import QMenu
        end = time.time() + seconds
        g = w.viewport.mapToGlobal(QPoint(w.viewport.width() // 2, w.viewport.height() // 3))
        while time.time() < end:
            m = QMenu(w)
            for label in ("파일 열기", "재생", "재생 속도", "자막", "캡처", "재생 정보", "PIP", "전체화면", "종료"):
                m.addAction(label)
            m.popup(g)
            pump(0.6)
            m.hide()
            m.deleteLater()
            pump(0.3)

    def sc_dialog(seconds):
        """The controller-settings dialog (the gear button) is a separate top-level window."""
        from ui.glass_controller import ControllerSettingsDialog
        end = time.time() + seconds
        while time.time() < end:
            d = ControllerSettingsDialog(w.controller.current_layout, w)
            # park it where it cannot cover the sampled pixels (it centers on the window by default)
            d.move(w.x() + w.width() - d.width() - 10, w.y() + w.height() - d.height() - 10)
            d.show()
            pump(0.7)
            d.close()
            d.deleteLater()
            pump(0.3)

    def sc_fullscreen(seconds):
        sampler.mode = "strip"
        for _ in range(3):
            w.toggle_fullscreen(); pump(1.0)
            w.toggle_fullscreen(); pump(1.0)
        sampler.mode = "points"

    def sc_pip(seconds):
        sampler.mode = "strip"
        for _ in range(2):
            w.toggle_pip_mode(); pump(1.2)
            w.toggle_pip_mode(); pump(1.2)
        sampler.mode = "points"

    SCENARIOS = [
        ("steady", "재생 (컨트롤 표시)", sc_steady),
        ("hidden", "재생 (컨트롤 숨김)", sc_hidden),
        ("paused", "일시정지", sc_paused),
        ("fade", "컨트롤 페이드 인/아웃 반복", sc_fade),
        ("mouse", "마우스를 영상 위에서 계속 움직임", sc_mouse),
        ("popups", "배속·정보·볼륨 패널 열고 닫기", sc_popups),
        ("osd", "OSD 메시지 반복 (배속 변경)", sc_osd),
        ("move", "창 이동", sc_move),
        ("resize", "창 크기 변경", sc_resize),
        ("menu", "우클릭 메뉴 열고 닫기", sc_menu),
        ("dialog", "설정(⚙) 창 열고 닫기", sc_dialog),
        ("fullscreen", "전체화면 전환", sc_fullscreen),
        ("pip", "PIP 전환", sc_pip),
    ]
    only = set(args.only.split(",")) if args.only else None

    # ---------------- run ----------------
    w.load_media_file(clip)
    w.engine.mpv.loop_file = "inf"
    pump(1.5)
    update_points()
    sampler.start()
    pump(0.5)

    results = []
    for key, title, fn in SCENARIOS:
        if only and key not in only:
            continue
        w.controller.hold_visible = None
        w.toggle_media_info() if w.info_panel.isVisible() else None
        w.speed_popup.hide()
        pump(0.8)
        t_start = time.perf_counter()
        runs0, p0 = len(sampler.bad_runs), len(paints)
        fn(args.seconds)
        t_end = time.perf_counter()
        runs = [(s, d) for s, d in sampler.bad_runs[runs0:] if t_start <= s <= t_end]
        scenario_paints = [(t, d) for t, d in paints[p0:] if t_start <= t <= t_end]
        results.append((key, title, t_end - t_start, runs, scenario_paints, sampler.samples))
        detail = ", ".join(f"+{(st - t_start):.2f}s {d * 1000:.0f}ms" for st, d in runs)
        print(f"[probe] {title}: {len(runs)} blank(s)" + (f"  [{detail}]" if runs else ""), flush=True)

    sampler.stop_flag = True
    sampler.join(timeout=2)
    w.close()

    # ---------------- report ----------------
    print("\n" + "=" * 78)
    print(f"{'시나리오':32s} {'시간':>6s} {'공백':>5s} {'최장공백':>9s} {'그린횟수':>8s} {'평균간격':>8s} {'최대간격':>8s} {'렌더평균':>8s} {'렌더최대':>8s}")
    for key, title, dur, runs, sp, _n in results:
        gaps = [(b[0] - a[0]) * 1000 for a, b in zip(sp, sp[1:])]
        longest = max((d for _s, d in runs), default=0) * 1000
        print(f"{title:30s} {dur:5.1f}s {len(runs):5d} {longest:7.0f}ms {len(sp):8d} "
              f"{(statistics.mean(gaps) if gaps else 0):6.1f}ms {(max(gaps) if gaps else 0):6.0f}ms "
              f"{(statistics.mean([d for _t, d in sp]) * 1000 if sp else 0):6.1f}ms "
              f"{(max((d for _t, d in sp), default=0) * 1000):6.1f}ms")
    print("=" * 78)
    print("공백 = 영상 픽셀이 기대한 색에서 벗어난 연속 구간 (>=2 지점). 33ms(30fps 한 프레임) 안팎이면 한 프레임 깜빡임.")
    total = sum(len(r[3]) for r in results)
    print(f"전체 공백 {total}건; 샘플 {sampler.samples}회")
    return results


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--clip", help="video to play (default: generated color-bar clip)")
    ap.add_argument("--only", help="comma-separated scenario keys")
    ap.add_argument("--block", action="store_true", help="comparison: render() blocks for the target time (the old behaviour)")
    ap.add_argument("--seconds", type=float, default=4.0, help="length of each scenario")
    run(ap.parse_args())
