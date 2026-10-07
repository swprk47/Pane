"""Playing on to the next video of the folder: the card, the buttons, the keys and the setting."""
import os
import shutil

import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QWidget

import ui.main_window as mw
from core.settings import AppSettings
from ui.next_up import NextUpCard, NEXT_UP_SECONDS


@pytest.fixture
def episodes(tmp_path, sample_video):
    """ep1, ep2, ep10 (natural order: 1, 2, 10), real playable files."""
    paths = {}
    for n in ("ep1.mp4", "ep2.mp4", "ep10.mp4"):
        shutil.copy(sample_video, tmp_path / n)
        paths[n] = str(tmp_path / n)
    return paths


def current(window):
    return os.path.basename(window._current_file or "")


@pytest.fixture(autouse=True)
def mouse_away_from_card(monkeypatch):
    """Where the real cursor happens to be must not hold a countdown (tests that need it over the card say so)."""
    monkeypatch.setattr(NextUpCard, "_mouse_over", lambda self: False)


# --- the card on its own ----------------------------------------------------

def test_card_counts_down_and_then_finishes(qapp, pump):
    host = QWidget()
    host.resize(600, 400)
    host.show()
    card = NextUpCard(host)
    done = []
    card.finished.connect(lambda: done.append("finished"))
    card.start("ep3.mp4", 0.4)
    assert card.isVisible() and card.is_counting()
    first = card.remaining()
    pump(timeout=0.15)
    assert card.remaining() < first
    assert pump(lambda: done, timeout=2.0)
    assert not card.isVisible() and not card.is_counting()


def test_card_holds_while_the_mouse_is_on_it_and_goes_on_from_there(qapp, pump, monkeypatch):
    host = QWidget()
    host.resize(600, 400)
    host.show()
    card = NextUpCard(host)
    done = []
    card.finished.connect(lambda: done.append("finished"))
    card.start("ep3.mp4", 0.5)
    monkeypatch.setattr(NextUpCard, "_mouse_over", lambda self: True)
    pump(timeout=0.15)
    assert card.is_held()
    held_at = card.remaining()
    pump(timeout=0.8)                                # longer than the whole countdown
    assert not done and card.is_counting()
    assert card.remaining() == pytest.approx(held_at, abs=0.05), "the time stands still under the mouse"
    monkeypatch.setattr(NextUpCard, "_mouse_over", lambda self: False)
    assert pump(lambda: done, timeout=2.0), "it finishes after the mouse leaves"
    assert not card.is_held()


def test_card_counts_five_seconds_by_default():
    assert NEXT_UP_SECONDS == 5.0


def test_card_cancel_and_play_now_each_end_it_once(qapp):
    host = QWidget()
    host.resize(600, 400)
    host.show()
    card = NextUpCard(host)
    events = []
    card.cancelled.connect(lambda: events.append("cancelled"))
    card.play_now.connect(lambda: events.append("play_now"))
    card.finished.connect(lambda: events.append("finished"))
    card.start("a.mp4", 5.0)
    card.cancel()
    card.cancel()                                   # a second cancel does nothing
    assert events == ["cancelled"] and not card.isVisible()
    card.start("b.mp4", 5.0)
    card.btn_play.click()
    card.btn_play.click()
    assert events == ["cancelled", "play_now"]
    card.start("c.mp4", 5.0)
    card.btn_cancel.click()
    assert events[-1] == "cancelled"


def test_card_is_hidden_until_started(qapp):
    host = QWidget()
    host.show()
    assert not NextUpCard(host).isVisible()


# --- the window: buttons and keys ---------------------------------------------

def test_previous_and_next_buttons_follow_the_folder(window, episodes):
    c = window.controller
    window.load_media_file(episodes["ep2.mp4"])
    assert c.btn_prev_file.isEnabled() and c.btn_next_file.isEnabled()
    window.load_media_file(episodes["ep1.mp4"])
    assert not c.btn_prev_file.isEnabled() and c.btn_next_file.isEnabled()
    window.load_media_file(episodes["ep10.mp4"])
    assert c.btn_prev_file.isEnabled() and not c.btn_next_file.isEnabled()


def test_buttons_are_disabled_for_a_lone_file(window, sample_video, tmp_path):
    lone = tmp_path / "lone.mp4"
    shutil.copy(sample_video, lone)
    window.load_media_file(str(lone))
    assert not window.controller.btn_prev_file.isEnabled() and not window.controller.btn_next_file.isEnabled()


def test_next_and_previous_use_natural_order(window, episodes):
    window.load_media_file(episodes["ep2.mp4"])
    window.play_adjacent(+1)
    assert current(window) == "ep10.mp4", "ep2 is followed by ep10, not ep10 before ep2"
    window.play_adjacent(-1)
    assert current(window) == "ep2.mp4"
    window.play_adjacent(-1)
    assert current(window) == "ep1.mp4"


def test_at_either_end_it_stays_and_says_so(window, episodes):
    window.load_media_file(episodes["ep1.mp4"])
    window.play_adjacent(-1)
    assert current(window) == "ep1.mp4" and window.osd.text_label.text() == "첫 영상입니다"
    window.load_media_file(episodes["ep10.mp4"])
    window.play_adjacent(+1)
    assert current(window) == "ep10.mp4" and window.osd.text_label.text() == "마지막 영상입니다"


@pytest.mark.parametrize("key,expected", [(Qt.Key_Greater, "ep10.mp4"), (Qt.Key_PageDown, "ep10.mp4"),
                                          (Qt.Key_Less, "ep1.mp4"), (Qt.Key_PageUp, "ep1.mp4")])
def test_keys_move_between_videos(window, episodes, key, expected):
    window.load_media_file(episodes["ep2.mp4"])
    QTest.keyClick(window, key)
    assert current(window) == expected


def test_the_frame_step_keys_still_work(window, episodes):
    """Shift+. / Shift+, are the video keys; plain . and , stay frame steps."""
    window.load_media_file(episodes["ep2.mp4"])
    QTest.keyClick(window, Qt.Key_Period)
    QTest.keyClick(window, Qt.Key_Comma)
    assert current(window) == "ep2.mp4"


def test_controller_buttons_open_the_neighbours(window, episodes):
    window.load_media_file(episodes["ep2.mp4"])
    window.controller.btn_next_file.click()
    assert current(window) == "ep10.mp4"
    window.controller.btn_prev_file.click()
    assert current(window) == "ep2.mp4"


# --- the window: the end of a video -------------------------------------------

@pytest.fixture
def quick_card(monkeypatch):
    monkeypatch.setattr(mw, "NEXT_UP_SECONDS", 0.5)


def end_of_file(window):
    """Run the file to its end (the sample is 3 s long)."""
    window.engine.set_speed(4.0)


def test_the_next_video_starts_by_itself_after_the_card(window, episodes, quick_card, pump):
    window.load_media_file(episodes["ep1.mp4"])
    end_of_file(window)
    assert pump(lambda: window.next_up.is_counting(), timeout=8.0), "the card appears when the video ends"
    assert window.next_up._name == "ep2.mp4"
    assert pump(lambda: current(window) == "ep2.mp4", timeout=4.0), "...and the next video starts after the countdown"
    assert not window.next_up.isVisible()


def test_escape_keeps_you_on_this_video(window, episodes, quick_card, pump):
    window.load_media_file(episodes["ep1.mp4"])
    end_of_file(window)
    assert pump(lambda: window.next_up.is_counting(), timeout=8.0)
    QTest.keyClick(window, Qt.Key_Escape)
    assert not window.next_up.isVisible()
    pump(timeout=1.0)
    assert current(window) == "ep1.mp4"


def test_play_now_does_not_wait_for_the_countdown(window, episodes, monkeypatch, pump):
    monkeypatch.setattr(mw, "NEXT_UP_SECONDS", 30.0)
    window.load_media_file(episodes["ep1.mp4"])
    end_of_file(window)
    assert pump(lambda: window.next_up.is_counting(), timeout=8.0)
    window.next_up.btn_play.click()
    assert current(window) == "ep2.mp4"


def test_restarting_the_video_cancels_the_countdown(window, episodes, monkeypatch, pump):
    monkeypatch.setattr(mw, "NEXT_UP_SECONDS", 30.0)
    window.load_media_file(episodes["ep1.mp4"])
    end_of_file(window)
    assert pump(lambda: window.next_up.is_counting(), timeout=8.0)
    window.engine.toggle_play()                      # play at the end = watch it again, so stay here
    assert pump(lambda: not window.next_up.isVisible(), timeout=1.5)
    assert current(window) == "ep1.mp4"


def test_seeking_cancels_the_countdown(window, episodes, monkeypatch, pump):
    monkeypatch.setattr(mw, "NEXT_UP_SECONDS", 30.0)
    window.load_media_file(episodes["ep1.mp4"])
    end_of_file(window)
    assert pump(lambda: window.next_up.is_counting(), timeout=8.0)
    window.seek_relative(-1.0)
    assert not window.next_up.is_counting()


def test_the_last_video_just_says_it_is_finished(window, episodes, pump):
    window.load_media_file(episodes["ep10.mp4"])
    end_of_file(window)
    assert pump(lambda: window.osd.text_label.text() == "재생 완료", timeout=8.0)
    assert not window.next_up.isVisible()


def test_with_auto_next_off_nothing_follows(window, episodes, pump):
    window.app_settings.set_auto_next(False)
    window.load_media_file(episodes["ep1.mp4"])
    end_of_file(window)
    assert pump(lambda: window.osd.text_label.text() == "재생 완료", timeout=8.0)
    assert not window.next_up.isVisible() and current(window) == "ep1.mp4"


def test_a_pending_card_is_dropped_when_another_file_is_opened(window, episodes, monkeypatch, pump):
    monkeypatch.setattr(mw, "NEXT_UP_SECONDS", 30.0)
    window.load_media_file(episodes["ep1.mp4"])
    end_of_file(window)
    assert pump(lambda: window.next_up.is_counting(), timeout=8.0)
    window.load_media_file(episodes["ep10.mp4"])
    assert not window.next_up.is_counting() and window._next_target is None


# --- the setting and the layout ------------------------------------------------

def test_auto_next_defaults_to_on_and_is_remembered():
    s = AppSettings()
    assert s.get_auto_next() is True
    s.set_auto_next(False)
    assert AppSettings().get_auto_next() is False
    s.set_auto_next(True)
    assert AppSettings().get_auto_next() is True


def test_default_layout_has_the_video_buttons_at_the_two_ends():
    from ui.glass_controller import DEFAULT_LAYOUT, LAYOUT_VERSION
    center = DEFAULT_LAYOUT["center"]
    assert center[0] == "prev_file" and center[-1] == "next_file" and "play_pause" in center
    assert LAYOUT_VERSION >= 5, "an older saved layout must be reset once so the new buttons appear"
    assert "prev_frame" not in center and "next_frame" not in center, "frame stepping stays on , and . (buttons are optional)"


def test_a_disabled_button_is_dimmed_and_shows_the_arrow_cursor(qapp):
    from PySide6.QtGui import QColor, QImage, QPainter
    from ui.glass_button import GlassButton
    from ui.icons import get_svg_icon
    host = QWidget()
    host.resize(100, 100)
    host.show()
    b = GlassButton(host, "plain", 40, 22)
    b.setIcon(get_svg_icon("skip_next_glass", size=22, color="#FFFFFF"))
    b.show()

    def icon_luma():
        img = QImage(b.size(), QImage.Format_ARGB32)
        img.fill(QColor(0, 0, 0))
        p = QPainter(img)
        b.render(p, QPoint(0, 0))
        p.end()
        return max(img.pixelColor(x, y).red() for x in range(40) for y in range(40))
    on = icon_luma()
    b.setEnabled(False)
    off = icon_luma()
    assert off < on * 0.6 and b.cursor().shape() == Qt.ArrowCursor
    b.setEnabled(True)
    assert b.cursor().shape() == Qt.PointingHandCursor
