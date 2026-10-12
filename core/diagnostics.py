"""
The text a user can paste to us when something looks wrong: app/Windows/GPU/screen/mpv
versions, what is playing right now and the tail of pane.log.

Built only on demand (the About dialog's copy button), so it costs nothing while playing.
Personal paths are scrubbed: the user profile folder becomes %USERPROFILE%, the user name
`<user>`, and only the file *name* of the current video is included.
"""
import ctypes
import os
import platform
import re
import sys
from pathlib import Path

from core import app_log, media_info
from core.version import APP_NAME, APP_VERSION

LOG_LINES = 80


# --- privacy ---------------------------------------------------------------

def scrub(text: str) -> str:
    """Replace the user profile folder (either slash style, any case) and the user name."""
    home = Path.home()
    for variant in {str(home), str(home).replace("\\", "/")}:
        text = re.sub(re.escape(variant), "%USERPROFILE%", text, flags=re.IGNORECASE)
    if home.name:
        text = re.sub(rf"(?<![\w]){re.escape(home.name)}(?![\w])", "<user>", text, flags=re.IGNORECASE)
    return text


_START = re.compile(r"^=== .* start ===$")


def log_tail(path, lines: int = LOG_LINES) -> str:
    """Last `lines` lines of pane.log. Runs that logged nothing (most of them) are folded into
    one summary line; runs with output keep their `=== start ===` header."""
    try:
        content = Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return "(기록 파일이 없음)"
    runs = []                       # [header or None, [lines]]
    for line in content.splitlines():
        if _START.match(line):
            runs.append([line, []])
        elif line.strip():
            if not runs:
                runs.append([None, []])
            runs[-1][1].append(line)
    quiet = sum(1 for _, body in runs if not body)
    out = []
    for header, body in runs:
        if body:
            out += ([header] if header else []) + body
    out = out[-lines:]
    starts = sum(1 for header, _ in runs if header)
    if quiet == len(runs):
        return f"({starts}회 실행, 오류 없음)"
    summary = [f"({starts}회 실행 중 {quiet}회는 기록 없음)"] if starts else []
    return "\n".join(summary + out)


# --- environment -----------------------------------------------------------

def windows_version() -> str:
    try:
        v = sys.getwindowsversion()
        name = "Windows 11" if (v.major, v.build) >= (10, 22000) else f"Windows {v.major}"
        return f"{name} (빌드 {v.build}, {platform.machine()})"
    except Exception:
        return platform.platform()


class _DisplayDevice(ctypes.Structure):
    _fields_ = [("cb", ctypes.c_ulong), ("DeviceName", ctypes.c_wchar * 32),
                ("DeviceString", ctypes.c_wchar * 128), ("StateFlags", ctypes.c_ulong),
                ("DeviceID", ctypes.c_wchar * 128), ("DeviceKey", ctypes.c_wchar * 128)]


def gpu_adapters() -> list:
    """Display adapter names (a cheap Win32 call, no subprocess)."""
    names = []
    try:
        i = 0
        while True:
            dev = _DisplayDevice()
            dev.cb = ctypes.sizeof(dev)
            if not ctypes.windll.user32.EnumDisplayDevicesW(None, i, ctypes.byref(dev), 0):
                break
            if dev.DeviceString and dev.DeviceString not in names:
                names.append(dev.DeviceString)
            i += 1
    except Exception:
        pass
    return names


def describe_screens(screens) -> list:
    """['2560×1440 @ 144 Hz · 배율 150%', ...] from Qt screens."""
    out = []
    for s in screens:
        size = s.size()
        ratio = int(round(s.devicePixelRatio() * 100))
        out.append(f"{size.width()}×{size.height()} @ {round(s.refreshRate())} Hz · 배율 {ratio}%")
    return out


# --- report ----------------------------------------------------------------

def _prop(mpv, name):
    try:
        return mpv._get_property(name)
    except Exception:
        return None


def _plain(value):
    """mpv returns some options (hwdec) as lists."""
    if isinstance(value, (list, tuple)):
        return ", ".join(str(v) for v in value)
    return value


def build_report(mpv, screens=(), log_path=None, gpus=None, problem=None) -> str:
    gpus = gpu_adapters() if gpus is None else gpus
    packaged = "설치본" if getattr(sys, "frozen", False) else "소스 실행"
    lines = [
        f"{APP_NAME} v{APP_VERSION} ({packaged})",
        windows_version(),
        "GPU: " + (", ".join(gpus) if gpus else "알 수 없음"),
    ]
    lines += [f"화면 {i}: {s}" for i, s in enumerate(screens, 1)]
    lines += [
        f"mpv: {_prop(mpv, 'mpv-version') or '?'}",
        f"FFmpeg: {_prop(mpv, 'ffmpeg-version') or '?'}",
        f"디코더 설정: {_plain(_prop(mpv, 'hwdec')) or '?'} (사용 중: {_prop(mpv, 'hwdec-current') or '없음'})",
        "",
    ]

    info = media_info.read_media_info(mpv)
    path = info.get("path")
    if path or info.get("video_format"):
        lines.append(f"영상 파일: {os.path.basename(str(path)) if path else '?'}")
        lines.append(media_info.to_plain_text(media_info.describe(info)))
    else:
        lines.append("재생 중인 영상 없음")

    if problem:
        lines += ["", "[마지막 파일 오류]", problem]
    if log_path is None and not getattr(sys, "frozen", False):
        log = "(소스 실행: 기록을 남기지 않음)"      # pane.log may hold the installed app's old runs
    else:
        log = log_tail(log_path or app_log.log_path())
    lines += ["", f"[최근 기록 (마지막 {LOG_LINES}줄)]", log]
    return scrub("\n".join(lines))
