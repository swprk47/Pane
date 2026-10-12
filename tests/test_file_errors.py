"""A file that cannot be opened: what mpv says, how it is put in plain words, and the start screen that shows it."""
import os

import pytest
from PySide6.QtCore import QPoint
from PySide6.QtGui import QImage, QRegion
from PySide6.QtWidgets import QWidget

from core import diagnostics
from core.file_errors import classify
from core.settings import AppSettings


@pytest.fixture
def text_file(tmp_path):
    p = tmp_path / "notes.mp4"
    p.write_text("this is not a video at all\n" * 50)
    return str(p)


@pytest.fixture
def empty_file(tmp_path):
    p = tmp_path / "empty.mp4"
    p.write_bytes(b"")
    return str(p)


# --- putting it in words -----------------------------------------------------

def test_not_a_video_or_damaged(text_file):
    p = classify(text_file, "unrecognized file format", ["lavf: avformat_open_input() failed"])
    assert p.kind == "unrecognized"
    assert "notes.mp4" in p.title and "열 수 없어요" in p.title
    assert "손상" in p.hint and "다운로드" in p.hint


def test_an_empty_file_says_so_even_though_mpv_calls_it_unrecognized(empty_file):
    p = classify(empty_file, "unrecognized file format", [])
    assert p.kind == "empty"
    assert "비어 있어요" in p.title


def test_a_missing_file(tmp_path):
    p = classify(str(tmp_path / "gone.mp4"), "loading failed", [])
    assert p.kind == "missing"
    assert "찾을 수 없어요" in p.title and "gone.mp4" in p.title
    assert "드라이브" in p.hint


def test_permission_denied_or_in_use(text_file):
    p = classify(text_file, "loading failed", ["file: Cannot open file 'x': Permission denied"])
    assert p.kind == "denied"
    assert "다른 프로그램" in p.hint


def test_something_unexpected_still_gets_an_honest_message(text_file):
    p = classify(text_file, "some new mpv wording", ["whatever: broke"])
    assert p.kind == "unknown"
    assert "notes.mp4" in p.title
    assert "진단 정보" in p.hint


def test_the_detail_keeps_what_mpv_said_for_the_diagnostics(text_file):
    p = classify(text_file, "unrecognized file format", ["lavf: avformat_open_input() failed", "ffmpeg/demuxer: moov atom not found"])
    assert "unrecognized file format" in p.detail and "moov atom not found" in p.detail


# --- from mpv to the signal --------------------------------------------------

def test_the_engine_reports_a_file_mpv_cannot_open(engine, pump, text_file):
    got = []
    engine.load_failed.connect(lambda path, err, logs: got.append((path, err, logs)))
    engine.load_file(text_file)
    assert pump(lambda: bool(got), timeout=5)
    path, err, logs = got[0]
    assert path == text_file and err == "unrecognized file format"


def test_the_engine_reports_an_empty_file_too(engine, pump, empty_file):
    got = []
    engine.load_failed.connect(lambda *a: got.append(a))
    engine.load_file(empty_file)
    assert pump(lambda: bool(got), timeout=5)


def test_a_good_file_reports_no_failure(engine, pump, sample_video):
    got = []
    engine.load_failed.connect(lambda *a: got.append(a))
    engine.load_file(sample_video)
    pump(None, timeout=1.0)
    assert got == []


# --- the start screen ----------------------------------------------------------

def render(widget) -> QImage:
    img = QImage(widget.size(), QImage.Format_ARGB32_Premultiplied)
    img.fill(0)
    widget.render(img, QPoint(), QRegion(), QWidget.RenderFlag(0))
    return img


def orange_pixels(img) -> int:
    n = 0
    for y in range(img.height()):
        for x in range(img.width()):
            c = img.pixelColor(x, y)
            if c.red() > 180 and c.green() > 100 and (c.red() - c.blue()) > 70:
                n += 1
    return n


def test_the_start_screen_shows_a_problem_instead_of_the_drop_hint(window):
    s = window.viewport.start_screen
    window.viewport.show_empty_notice(True)
    s.resize(900, 600)
    assert not s.has_problem()
    before = orange_pixels(render(s))
    s.set_problem("‘notes.mp4’ 파일을 열 수 없어요", "영상 파일이 아니거나 손상된 것 같아요.")
    assert s.has_problem() and s.problem_title().startswith("‘notes.mp4’")
    assert orange_pixels(render(s)) > before + 20, "the notice is drawn in the warning colour"
    s.clear_problem()
    assert not s.has_problem()


def test_the_notice_has_a_copy_link_that_asks_for_the_diagnostics(window):
    s = window.viewport.start_screen
    got = []
    s.copy_requested.connect(lambda: got.append(1))
    s.set_problem("t", "h")
    assert s.btn_copy.isVisible()
    s.btn_copy.click()
    assert got == [1]
    s.clear_problem()
    assert not s.btn_copy.isVisible()


@pytest.mark.parametrize("w,h", [(640, 380), (480, 270), (1060, 640), (1920, 1080)])
def test_the_notice_never_runs_into_the_dock_or_the_top_edge(window, w, h):
    """640x380 is the smallest window, 480x270 the PIP size: the logo, then the name, give way."""
    s = window.viewport.start_screen
    s.resize(w, h)
    s.set_problem("‘강의_4주차_녹화본(1).mp4’ 파일을 열 수 없어요", "영상 파일이 아니거나 손상된 것 같아요. 다운로드가 끝나지 않은 파일일 수도 있어요.")
    g = s._group()
    assert s.btn_copy.geometry().bottom() < s.dock_rect().top(), "the link must not sit under the dock"
    assert g["below_y"] + g["card_h"] <= s.dock_rect().top() - 8
    assert g["below_y"] >= 32, "nor under the window buttons (the middle of the title bar is free)"


def test_in_a_small_window_the_logo_gives_way_to_the_notice(window):
    s = window.viewport.start_screen
    s.resize(1060, 640)
    s.set_problem("t", "h")
    assert s._group()["size"] > 0
    s.resize(640, 380)
    assert s._group()["size"] == 0 and s._group()["show_name"]
    s.resize(480, 270)
    assert not s._group()["show_name"]


# --- in the player -----------------------------------------------------------

def test_opening_a_bad_file_ends_on_the_start_screen_with_the_reason(window, pump, text_file):
    w = window
    w.load_media_file(text_file)
    assert pump(lambda: w.viewport.start_screen.has_problem(), timeout=5)
    s = w.viewport.start_screen
    assert s.isVisible() and "notes.mp4" in s.problem_title()
    assert w._current_file is None, "nothing is open"
    assert not w.controller.isVisible(), "no controls over an empty screen"
    assert not w.top_scrim.isVisible()


def test_a_bad_file_is_not_offered_for_resuming(window, pump, text_file):
    w = window
    w.load_media_file(text_file)
    assert pump(lambda: w.viewport.start_screen.has_problem(), timeout=5)
    assert text_file not in AppSettings().get_recent_files()
    assert not w.viewport.start_screen.has_resume() or w.viewport.start_screen.resume_info()["path"] != text_file


def test_a_missing_file_is_explained_at_once_without_asking_mpv(window):
    w = window
    w.load_media_file(os.path.join(os.getcwd(), "definitely_not_here.mp4"))
    s = w.viewport.start_screen
    assert s.has_problem() and "찾을 수 없어요" in s.problem_title()
    assert w._current_file is None


def test_opening_a_good_file_afterwards_clears_the_notice(window, pump, text_file, sample_video):
    w = window
    w.load_media_file(text_file)
    assert pump(lambda: w.viewport.start_screen.has_problem(), timeout=5)
    w.load_media_file(sample_video)
    assert not w.viewport.start_screen.has_problem()
    assert w._current_file == sample_video


def test_the_notice_is_also_in_the_diagnostics(window, pump, text_file):
    w = window
    w.load_media_file(text_file)
    assert pump(lambda: w.viewport.start_screen.has_problem(), timeout=5)
    report = w.diagnostics_text()
    assert "[마지막 파일 오류]" in report and "unrecognized" in report


def test_the_notice_link_copies_the_diagnostics(window, pump, text_file, qapp):
    w = window
    w.load_media_file(text_file)
    assert pump(lambda: w.viewport.start_screen.has_problem(), timeout=5)
    qapp.clipboard().setText("")
    w.viewport.start_screen.btn_copy.click()
    assert "[마지막 파일 오류]" in qapp.clipboard().text()


def test_the_report_has_no_problem_section_when_all_went_well(tmp_path):
    class Mpv:
        def _get_property(self, name):
            raise RuntimeError(name)
    text = diagnostics.build_report(Mpv(), screens=[], log_path=tmp_path / "x.log", gpus=["g"])
    assert "[마지막 파일 오류]" not in text
    text = diagnostics.build_report(Mpv(), screens=[], log_path=tmp_path / "x.log", gpus=["g"], problem="x.mp4: unrecognized")
    assert "[마지막 파일 오류]" in text and "x.mp4: unrecognized" in text


# --- opening from Windows (the file association) --------------------------------

def test_a_file_given_at_startup_is_passed_on_even_if_it_is_gone():
    import main
    assert main.startup_file(["Pane.exe", r"D:\moved\lecture.mp4"]) == r"D:\moved\lecture.mp4"
    assert main.startup_file(["Pane.exe"]) is None
    assert main.startup_file(["Pane.exe", "--some-flag"]) is None


# --- remembered files -----------------------------------------------------------

def test_a_file_can_be_forgotten_from_the_recent_list():
    s = AppSettings()
    s.add_recent_file("a.mp4")
    s.add_recent_file("b.mp4")
    s.remove_recent_file("a.mp4")
    assert s.get_recent_files() == ["b.mp4"]
    s.remove_recent_file("not-there.mp4")
    assert s.get_recent_files() == ["b.mp4"]


def test_the_report_also_has_the_mpv_lines_that_came_just_after_the_failure(window, pump, text_file):
    """mpv logs "Failed to recognize file format" a moment after it reports the failed load."""
    w = window
    w.load_media_file(text_file)
    assert pump(lambda: w.viewport.start_screen.has_problem(), timeout=5)
    assert pump(lambda: "Failed to recognize file format" in w.diagnostics_text(), timeout=3)
