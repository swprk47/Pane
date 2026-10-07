"""The start screen: logo, hint, the glass dock with "영상 열기" and the last video to go on with."""
import os

import pytest
from PySide6.QtCore import QMimeData, QPoint, QPointF, QUrl, Qt
from PySide6.QtGui import QDragEnterEvent, QDragLeaveEvent, QDropEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QWidget

from core.settings import AppSettings
from ui.start_screen import StartScreen, format_time, TOP_SAFE


@pytest.fixture
def screen(qapp):
    host = QWidget()
    host.resize(880, 520)
    s = StartScreen(host)
    s.setGeometry(0, 0, 880, 520)
    host.show()
    s.show()
    qapp.processEvents()
    yield s
    host.close()


# --- what it offers ------------------------------------------------------------

def test_format_time():
    assert format_time(7) == "00:07" and format_time(72) == "01:12" and format_time(3725) == "01:02:05"


def test_without_a_last_video_the_dock_is_just_the_open_button(screen):
    d = screen.dock_rect()
    assert not screen.has_resume() and not screen.btn_go.isVisible() and not screen.btn_resume.isVisible()
    assert d.width() < 200 and screen.btn_open.isVisible()
    assert abs(d.center().x() - screen.width() / 2) < 1


def test_a_video_that_was_left_midway_is_offered_to_go_on(screen):
    screen.set_resume("C:/v/movie.mp4", 72.0, 228.0)
    info = screen.resume_info()
    assert info["label"] == "이어보기" and info["name"] == "movie.mp4" and info["time"] == "01:12 / 03:48"
    assert info["ratio"] == pytest.approx(72 / 228)
    assert screen.btn_go.isVisible() and screen.btn_resume.isVisible()
    assert screen.dock_rect().width() >= 360


@pytest.mark.parametrize("position, duration, label, time", [
    (0.0, 30.0, "최근 영상", "00:30"),          # never watched far enough to be "left midway"
    (4.0, 30.0, "최근 영상", "00:30"),
    (29.0, 30.0, "최근 영상", "00:30"),         # watched to the end: it starts over
    (12.0, 0.0, "이어보기", "00:12"),           # length unknown (an older entry): just the time
])
def test_resume_label_and_time(screen, position, duration, label, time):
    screen.set_resume("C:/v/movie.mp4", position, duration)
    assert screen.resume_info()["label"] == label and screen.resume_info()["time"] == time
    if label == "최근 영상" or duration <= 0:
        assert screen.resume_info()["ratio"] == 0.0


def test_buttons_ask_for_the_dialog_or_the_last_video(screen, tmp_path):
    video = tmp_path / "last.mp4"
    video.write_bytes(b"x")
    events = []
    screen.open_requested.connect(lambda: events.append("open"))
    screen.resume_requested.connect(lambda p: events.append(p))
    screen.set_resume(str(video), 30.0, 100.0)
    screen.btn_open.click()
    screen.btn_go.click()
    screen.btn_resume.click()
    assert events == ["open", str(video), str(video)]
    video.unlink()
    screen.btn_go.click()
    assert events == ["open", str(video), str(video)], "a video that is gone is not opened"


def test_clear_resume_hides_the_dock_extras(screen):
    screen.set_resume("C:/v/movie.mp4", 30.0, 100.0)
    screen.clear_resume()
    assert not screen.has_resume() and not screen.btn_go.isVisible()


# --- layout ------------------------------------------------------------------------

@pytest.mark.parametrize("w, h", [(1060, 640), (640, 380), (1920, 1080)])
def test_dock_and_buttons_stay_inside_the_window(qapp, w, h):
    host = QWidget()
    host.resize(w, h)
    s = StartScreen(host)
    s.setGeometry(0, 0, w, h)
    s.set_resume("C:/v/" + "very_long_name_" * 8 + ".mp4", 30.0, 100.0)
    host.show()
    s.show()
    qapp.processEvents()
    d = s.dock_rect()
    assert d.left() >= 0 and d.right() <= w and d.bottom() <= h
    for b in (s.btn_open, s.btn_go, s.btn_resume):
        assert d.left() <= b.x() and b.x() + b.width() <= d.right() + 1, b
        assert d.top() <= b.y() and b.y() + b.height() <= d.bottom() + 1, b
    assert s.btn_open.x() + s.btn_open.width() < s.btn_go.x(), "the buttons never overlap"
    assert d.top() > TOP_SAFE + 100, "room left above the dock for the logo"
    host.close()


# --- drag over -----------------------------------------------------------------------

def test_dragging_a_file_over_lights_the_frame_up(window, tmp_path):
    video = tmp_path / "x.mp4"
    video.write_bytes(b"x")
    vp = window.viewport
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(video))])
    vp.dragEnterEvent(QDragEnterEvent(QPoint(50, 50), Qt.CopyAction, mime, Qt.LeftButton, Qt.NoModifier))
    assert vp.start_screen.is_dragging()
    vp.dragLeaveEvent(QDragLeaveEvent())
    assert not vp.start_screen.is_dragging()
    vp.dragEnterEvent(QDragEnterEvent(QPoint(50, 50), Qt.CopyAction, mime, Qt.LeftButton, Qt.NoModifier))
    got = []
    vp.file_dropped.connect(got.append)
    vp.dropEvent(QDropEvent(QPointF(50, 50), Qt.CopyAction, mime, Qt.LeftButton, Qt.NoModifier))
    assert [os.path.normpath(p) for p in got] == [str(video)] and not vp.start_screen.is_dragging()


# --- inside the window -----------------------------------------------------------------

def test_start_screen_is_the_empty_state_and_covers_the_viewport(window):
    vp = window.viewport
    assert vp.start_screen.isVisible() and vp.notice_widget is vp.start_screen
    assert vp.start_screen.geometry() == vp.rect()
    assert not vp.start_screen._logo.isNull()


def test_a_plain_click_on_the_start_screen_reaches_the_viewport_but_opens_nothing(window, monkeypatch):
    opened, clicks = [], []
    monkeypatch.setattr(window, "_open_file_dialog", lambda: opened.append(1))
    window.viewport.clicked.connect(lambda: clicks.append(1))
    QTest.mouseClick(window.viewport.start_screen, Qt.LeftButton, Qt.NoModifier, QPoint(60, 120))
    assert clicks == [1], "the press / release fall through to the viewport (that is what lets the window be dragged)"
    assert opened == [], "...but an empty click no longer opens the file dialog: that is the button's job"


def test_the_window_offers_its_most_recent_video_that_still_exists(window, tmp_path):
    a, b = tmp_path / "a.mp4", tmp_path / "b.mp4"
    a.write_bytes(b"x")
    b.write_bytes(b"x")
    s = AppSettings()
    s.add_recent_file(str(a))
    s.add_recent_file(str(b))
    s.save_resume_position(str(a), 40.0)
    s.save_duration(str(a), 100.0)
    window._refresh_start_screen()
    assert window.viewport.start_screen.resume_info()["name"] == "b.mp4"
    b.unlink()                                          # the newest one is gone: the next one is offered
    window._refresh_start_screen()
    info = window.viewport.start_screen.resume_info()
    assert info["name"] == "a.mp4" and info["time"] == "00:40 / 01:40" and info["label"] == "이어보기"
    a.unlink()
    window._refresh_start_screen()
    assert not window.viewport.start_screen.has_resume()


def test_loading_a_video_hides_the_start_screen_and_remembers_its_length(window, sample_video, pump):
    window.load_media_file(sample_video)
    assert not window.viewport.start_screen.isVisible()
    assert pump(lambda: window.app_settings.get_duration(sample_video) > 1.0, timeout=5.0), "the length is saved"


# --- settings ------------------------------------------------------------------------------

def test_duration_is_remembered_and_the_list_is_capped(qapp):
    s = AppSettings()
    assert s.get_duration("nope.mp4") == 0.0
    s.save_duration("a.mp4", 12.345)
    assert s.get_duration("a.mp4") == 12.35
    s.save_duration("a.mp4", 0.0)                       # nonsense is ignored
    s.save_duration("", 5.0)
    assert s.get_duration("a.mp4") == 12.35
    for i in range(60):
        s.save_duration(f"f{i}.mp4", 10.0 + i)
    assert s.get_duration("f59.mp4") == 69.0
    assert s.get_duration("f0.mp4") == 0.0, "only the last 50 are kept"


def test_the_version_sits_under_the_name_and_follows_core_version():
    from core.version import APP_VERSION
    from ui import start_screen
    assert start_screen.VERSION_TEXT == f"v{APP_VERSION}"
