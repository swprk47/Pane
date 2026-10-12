"""Diagnostics report: what a friend pastes to us when something looks wrong."""
from pathlib import Path

from core import diagnostics as dg
from core import version


class FakeMpv:
    def __init__(self, props=None):
        self.props = props or {}

    def _get_property(self, name):
        if name not in self.props:
            raise RuntimeError(name)
        return self.props[name]


def build(tmp_path, mpv=None, screens=("2560×1440 @ 144 Hz · 배율 150%",), log_text=None, **kw):
    log = tmp_path / "pane.log"
    if log_text is not None:
        log.write_text(log_text, encoding="utf-8")
    return dg.build_report(mpv or FakeMpv(), screens=list(screens), log_path=log,
                           gpus=kw.pop("gpus", ["Test GPU 1"]), **kw)


# --- scrubbing -------------------------------------------------------------

def test_scrub_hides_the_user_profile_folder():
    home = str(Path.home())
    out = dg.scrub(f"open {home}\\Videos\\a.mp4 failed")
    assert home not in out
    assert "%USERPROFILE%" in out and "a.mp4" in out


def test_scrub_hides_the_user_name_in_any_case_and_slash_style():
    home = Path.home()
    out = dg.scrub(f"{str(home).lower().replace(chr(92), '/')}/x and {home.name.upper()}")
    assert home.name.lower() not in out.lower()


# --- log tail --------------------------------------------------------------

def test_log_tail_keeps_only_the_last_lines(tmp_path):
    log = tmp_path / "pane.log"
    log.write_text("\n".join(f"line {i}" for i in range(500)), encoding="utf-8")
    tail = dg.log_tail(log, lines=80)
    assert tail.splitlines()[-1] == "line 499"
    assert len(tail.splitlines()) == 80
    assert "line 419" not in tail


def test_log_tail_without_a_log_file_says_so(tmp_path):
    assert "없" in dg.log_tail(tmp_path / "missing.log")


# --- the report ------------------------------------------------------------

def test_report_has_the_environment_sections(tmp_path):
    mpv = FakeMpv({"mpv-version": "mpv v0.41", "ffmpeg-version": "N-1", "hwdec-current": "d3d11va-copy"})
    text = build(tmp_path, mpv)
    assert f"v{version.APP_VERSION}" in text
    assert "Windows" in text
    assert "Test GPU 1" in text
    assert "2560×1440 @ 144 Hz" in text
    assert "mpv v0.41" in text and "N-1" in text


def test_report_never_contains_a_full_video_path(tmp_path):
    video = str(Path.home() / "Videos" / "secret.mp4")
    text = build(tmp_path, FakeMpv({"path": video, "video-format": "h264", "video-params/w": 1920, "video-params/h": 1080}))
    assert "secret.mp4" in text
    assert video not in text
    assert str(Path.home()) not in text


def test_report_marks_when_nothing_is_playing(tmp_path):
    assert "재생 중인 영상 없음" in build(tmp_path, FakeMpv({}))


def test_report_includes_playback_numbers_when_a_video_is_loaded(tmp_path):
    mpv = FakeMpv({"path": "C:/v/a.mp4", "video-format": "hevc", "video-params/w": 3840, "video-params/h": 2160,
                   "container-fps": 60.0, "hwdec-current": "d3d11va-copy",
                   "frame-drop-count": 12, "decoder-frame-drop-count": 3})
    text = build(tmp_path, mpv)
    assert "3840 × 2160" in text
    assert "HEVC" in text
    assert "12" in text      # dropped frames


def test_report_log_section_is_scrubbed(tmp_path):
    home = str(Path.home())
    text = build(tmp_path, log_text=f"error opening {home}\\Videos\\a.mp4\nsecond line")
    assert home not in text
    assert "second line" in text


def test_report_survives_a_broken_mpv(tmp_path):
    class Broken:
        def _get_property(self, name):
            raise OSError("mpv is gone")
    assert "v" + version.APP_VERSION in build(tmp_path, Broken())


def test_report_survives_gpu_lookup_failure(tmp_path):
    text = build(tmp_path, gpus=[])
    assert "GPU" in text


def test_real_environment_lookups_do_not_crash():
    assert isinstance(dg.windows_version(), str) and dg.windows_version()
    assert isinstance(dg.gpu_adapters(), list)


# --- About dialog ----------------------------------------------------------

def test_main_window_builds_a_diagnostic_report(window):
    text = window.diagnostics_text()
    assert f"v{version.APP_VERSION}" in text
    assert "mpv" in text


def test_about_dialog_copy_button_puts_the_report_on_the_clipboard(window, qapp):
    qapp.clipboard().setText("")
    window.copy_diagnostics()
    assert f"v{version.APP_VERSION}" in qapp.clipboard().text()


# --- readability -----------------------------------------------------------

def test_hwdec_setting_is_shown_as_plain_text_not_a_list(tmp_path):
    text = build(tmp_path, FakeMpv({"hwdec": ["auto-copy"], "hwdec-current": "d3d11va-copy"}))
    assert "디코더 설정: auto-copy" in text
    assert "[" not in text.split("디코더 설정:")[1].splitlines()[0]


def test_refresh_rate_is_rounded_and_scale_is_a_percentage():
    class Size:
        def width(self): return 2560
        def height(self): return 1440

    class Screen:
        def size(self): return Size()
        def refreshRate(self): return 143.998
        def devicePixelRatio(self): return 1.5
    assert dg.describe_screens([Screen()]) == ["2560×1440 @ 144 Hz · 배율 150%"]


def test_windows_11_is_named_by_build_number(monkeypatch):
    class V:
        major, minor, build = 10, 0, 26300
    monkeypatch.setattr(dg.sys, "getwindowsversion", lambda: V(), raising=False)
    assert dg.windows_version().startswith("Windows 11")
    V.build = 19045
    assert dg.windows_version().startswith("Windows 10")


# --- log compaction --------------------------------------------------------

LOG = (
    "\n=== 2026-10-08 11:23:46 start ===\n"
    "\n=== 2026-10-08 11:24:07 start ===\n[PlayerEngine] Seek error: boom\n"
    "\n=== 2026-10-10 01:05:16 start ===\n"
    "\n=== 2026-10-10 01:27:16 start ===\n"
    "\n=== 2026-10-12 02:04:39 start ===\nUNHANDLED ERROR:\nTraceback...\nValueError: x\n"
    "\n=== 2026-10-12 02:05:04 start ===\n"
)


def test_log_tail_folds_runs_that_logged_nothing(tmp_path):
    log = tmp_path / "pane.log"
    log.write_text(LOG, encoding="utf-8")
    tail = dg.log_tail(log)
    assert "start ===" in tail                       # runs with output keep their header
    assert tail.count("=== ") == 2                   # only the two runs that logged something
    assert "Seek error: boom" in tail and "ValueError: x" in tail
    assert "6회 실행" in tail and "4회는 기록 없음" in tail


def test_log_tail_with_only_empty_runs_is_one_line(tmp_path):
    log = tmp_path / "pane.log"
    log.write_text("\n=== 2026-10-08 11:23:46 start ===\n\n=== 2026-10-08 11:24:07 start ===\n", encoding="utf-8")
    tail = dg.log_tail(log)
    assert "오류 없음" in tail
    assert tail.count("\n") <= 1


def test_source_run_does_not_show_a_stale_installed_log(monkeypatch):
    monkeypatch.setattr(dg.sys, "frozen", False, raising=False)
    text = dg.build_report(FakeMpv(), screens=[], gpus=["g"])
    assert "소스 실행" in text.split("[최근 기록")[1]
