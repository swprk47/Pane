"""Bookmarks and chapters in the real main window: the chapter switch now, the keys and the pins as they are wired."""
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest

from core.settings import AppSettings


def click_switch(sw):
    QTest.mouseClick(sw, Qt.LeftButton, Qt.NoModifier, sw.rect().center())


def test_the_switch_saves_at_once_and_updates_the_window(window):
    assert window.chapters_on is True
    c = window.controller
    c._open_settings_dialog()
    p = c.settings_panel
    p.btn_tab_general.click()
    assert p.switch_chapters.checked is True
    click_switch(p.switch_chapters)
    assert AppSettings().get_chapters_visible() is False
    assert window.chapters_on is False
    p.reject()
    c._open_settings_dialog()
    q = c.settings_panel
    q.btn_tab_general.click()
    assert q.switch_chapters.checked is False, "the panel shows what was chosen"
    q.reject()


def test_the_panel_keeps_its_size(window):
    c = window.controller
    c._open_settings_dialog()
    p = c.settings_panel
    size = p.size()
    for button in (p.btn_tab_perf, p.btn_tab_audio, p.btn_tab_general, p.btn_tab_layout):
        button.click()
        assert p.size() == size
    p.reject()


# --- the keys, the pins, the panel and the pill, with a real video -----------------------------------------------------------

import shutil

import pytest
from PySide6.QtCore import QEvent, QPoint
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QLineEdit

from ui.bookmark_panel import _BookmarkRow
from ui.timeline_slider import PIN_COLOR

ALT = Qt.AltModifier


@pytest.fixture
def pills(window, monkeypatch):
    """Every OSD pill the window shows, as (text, icon, value)."""
    shown = []
    original = window.osd.show_message

    def record(text, icon="", value="", accent=False):
        shown.append((text, icon, value))
        original(text, icon, value, accent)

    monkeypatch.setattr(window.osd, "show_message", record)
    return shown


def load(window, path, pump):
    window.load_media_file(path)
    assert pump(lambda: window._duration > 0 and window.controller.timeline._duration > 0, timeout=10)
    window.engine.pause()
    pump(None, timeout=0.3)                              # (what mpv still had to say about the first frames)
    window._time_pos = 0.0


@pytest.fixture
def video(window, sample_video, pump, pills):
    load(window, sample_video, pump)
    pills.clear()
    return sample_video


def settle(window, pump, target):
    """The engine has arrived at `target` and what mpv still reported on the way (it tells the old position first) is
    through: the window's own idea of the position ends up there too."""
    assert pump(lambda: abs(window.engine._time_pos - target) < 0.1, timeout=5), f"the engine is at {target}"
    pump(None, timeout=0.3)
    assert abs(window._time_pos - target) < 0.1


def add_at(window, seconds):
    window._time_pos = seconds
    window.add_bookmark()


def stored(path):
    return AppSettings().get_bookmarks(path)


def test_b_adds_a_bookmark_at_the_current_time_and_says_so(window, video, pills):
    window._time_pos = 1.0
    QTest.keyClick(window, Qt.Key_B)
    assert pills[-1] == ("북마크", "bookmark", "0:01")
    assert window.bookmarks == [{"t": 1.0, "name": ""}] and stored(video) == window.bookmarks
    assert window.controller.timeline._bookmarks == [1.0], "the pin is on the bar"


def test_a_second_b_within_a_second_does_not_duplicate(window, video, pills):
    add_at(window, 1.0)
    window._time_pos = 1.4
    QTest.keyClick(window, Qt.Key_B)
    assert pills[-1] == ("이미 북마크가 있어요", "bookmark", "0:01")
    assert len(window.bookmarks) == 1 and len(stored(video)) == 1


def test_alt_right_and_alt_left_jump_between_bookmarks_and_never_seek_five_seconds(window, video, pills, pump):
    for t in (0.7, 1.8, 2.9):
        add_at(window, t)
    window._time_pos = 0.0
    pills.clear()
    for target in (0.7, 1.8, 2.9):
        QTest.keyClick(window, Qt.Key_Right, ALT)
        assert window._time_pos == target
        settle(window, pump, target)
    assert pills[-1][0] == "북마크" and pills[-1][2] == "0:02"
    QTest.keyClick(window, Qt.Key_Right, ALT)
    assert pills[-1][0] == "다음 북마크가 없어요" and window._time_pos == 2.9
    for target in (1.8, 0.7):
        QTest.keyClick(window, Qt.Key_Left, ALT)
        assert window._time_pos == target
        settle(window, pump, target)
    QTest.keyClick(window, Qt.Key_Left, ALT)
    assert pills[-1][0] == "이전 북마크가 없어요" and window._time_pos == 0.7


def test_b_and_the_jump_keys_do_nothing_without_a_video(window, pills):
    for key, mod in ((Qt.Key_B, Qt.NoModifier), (Qt.Key_B, Qt.ShiftModifier), (Qt.Key_Left, ALT), (Qt.Key_Right, ALT)):
        QTest.keyClick(window, key, mod)
    assert pills == [] and window.bookmark_panel is None and window.bookmarks == []
    assert AppSettings().get_bookmarks("") == []


def test_shift_b_and_the_button_open_the_panel_and_the_panel_acts(window, video, pills, qapp):
    add_at(window, 0.3)
    add_at(window, 1.5)
    QTest.keyClick(window, Qt.Key_B, Qt.ShiftModifier)
    panel = window.bookmark_panel
    assert panel.isVisible() and len(panel.findChildren(_BookmarkRow)) == 2
    panel.jump_requested.emit(1.5)
    assert window._time_pos == 1.5
    panel.rename_requested.emit(1.5, "증명")
    assert stored(video)[1] == {"t": 1.5, "name": "증명"} and window.bookmarks == stored(video)
    window._time_pos = 2.7
    panel.add_button.click()
    assert [b["t"] for b in stored(video)] == [0.3, 1.5, 2.7]
    assert len(panel.findChildren(_BookmarkRow)) == 3, "the open panel follows the change"
    panel.delete_requested.emit(0.3)
    assert [b["t"] for b in stored(video)] == [1.5, 2.7] and window.controller.timeline._bookmarks == [1.5, 2.7]
    window.controller.btn_bookmarks.click()
    assert not panel.isVisible(), "the button closes it again"
    window.controller.btn_bookmarks.click()
    assert panel.isVisible()


def test_keys_typed_in_the_rename_field_never_reach_the_player(window, video, pills, monkeypatch, qapp):
    add_at(window, 0.3)
    pills.clear()
    window.toggle_bookmark_panel()
    row = window.bookmark_panel.findChildren(_BookmarkRow)[0]
    row.edit_button.click()
    field = window.bookmark_panel.findChildren(QLineEdit)[0]
    assert window.bookmark_panel.is_editing
    played, seeks, screens = [], [], []
    monkeypatch.setattr(window.engine, "toggle_play", lambda: played.append(1))
    monkeypatch.setattr(window, "seek_relative", lambda s: seeks.append(s))
    monkeypatch.setattr(window, "toggle_fullscreen", lambda: screens.append(1))
    pos = window._time_pos
    for key, text in ((Qt.Key_B, "b"), (Qt.Key_Space, " "), (Qt.Key_Left, "")):
        QTest.keyClick(field, key)
        window.keyPressEvent(QKeyEvent(QEvent.KeyPress, key, Qt.NoModifier, text))      # (what a key the field left unhandled does)
    window.keyPressEvent(QKeyEvent(QEvent.KeyPress, Qt.Key_B, Qt.ShiftModifier, "B"))
    window.keyPressEvent(QKeyEvent(QEvent.KeyPress, Qt.Key_Right, ALT))
    assert played == [] and seeks == [] and len(window.bookmarks) == 1 and window._time_pos == pos and pills == []
    QTest.keyClick(field, Qt.Key_Return)
    assert screens == [], "Enter saves the name and does not toggle full screen"
    assert not window.bookmark_panel.is_editing


def test_opening_another_video_shows_that_videos_bookmarks(window, sample_video, pump, pills, tmp_path):
    other = str(tmp_path / "other.mp4")
    shutil.copy(sample_video, other)
    load(window, sample_video, pump)
    add_at(window, 1.0)
    assert window.controller.timeline._bookmarks == [1.0]
    load(window, other, pump)
    assert window.bookmarks == [] and window.controller.timeline._bookmarks == []
    add_at(window, 2.0)
    load(window, sample_video, pump)
    assert window.controller.timeline._bookmarks == [1.0] and window.bookmarks == [{"t": 1.0, "name": ""}]


def test_a_bookmark_beyond_the_length_is_not_drawn_nor_jumped_to(window, sample_video, pump, pills):
    AppSettings().save_bookmarks(sample_video, [{"t": 0.8, "name": ""}, {"t": 99.0, "name": ""}])
    load(window, sample_video, pump)
    assert len(window.controller.timeline._pin_marks()) == 1
    QTest.keyClick(window, Qt.Key_Right, ALT)
    assert window._time_pos == 0.8
    pills.clear()
    QTest.keyClick(window, Qt.Key_Right, ALT)
    assert pills[-1][0] == "다음 북마크가 없어요" and window._time_pos == 0.8


def test_clicking_a_pin_seeks_exactly_to_it(window, video, pump):
    add_at(window, 1.5)
    window._time_pos = 0.0
    tl = window.controller.timeline
    x = dict((t, px) for t, px in tl._pin_marks())[1.5]
    QTest.mouseClick(tl, Qt.LeftButton, Qt.NoModifier, QPoint(int(round(x)), tl.height() // 2))
    assert window._time_pos == 1.5
    assert pump(lambda: abs(window.engine._time_pos - 1.5) < 0.1, timeout=5)


def chapters_of(window, items):
    window.engine.chapters = lambda: items
    window._load_chapters()


def x_on_bar(window, seconds):
    tl = window.controller.timeline
    return tl._margin() + seconds / tl._duration * tl._span()


def test_the_pill_over_a_pin_shows_the_dot_name_and_time_and_over_a_chapter_the_chapter_name(window, video):
    chapters_of(window, [(0.0, "Intro"), (1.0, ""), (2.0, "Proofs")])
    tl, tip = window.controller.timeline, window.seek_tip
    tl.hover_moved.emit(1.2, x_on_bar(window, 1.2))
    assert (tip.text, tip.detail, tip.dot) == ("챕터 2", "0:01", None), "no title: the number"
    tl.hover_moved.emit(2.4, x_on_bar(window, 2.4))
    assert (tip.text, tip.detail, tip.dot) == ("Proofs", "0:02", None)
    tl.hover_moved.emit(0.4, x_on_bar(window, 0.4))
    assert (tip.text, tip.detail) == ("Intro", "0:00")
    add_at(window, 1.5)
    x = dict((t, px) for t, px in tl._pin_marks())[1.5]
    tl.hover_moved.emit(1.52, x)
    assert (tip.text, tip.detail, tip.dot) == ("0:01", "", PIN_COLOR), "a bookmark beats the chapter; no name: the time"
    window.rename_bookmark(1.5, "증명 다시 보기")
    tl.hover_moved.emit(1.52, x)
    assert (tip.text, tip.detail, tip.dot) == ("증명 다시 보기", "0:01", PIN_COLOR)
    tl.hover_left.emit()


def test_with_the_chapter_switch_off_there_are_no_gaps_and_no_chapter_name(window, video):
    chapters_of(window, [(0.0, "Intro"), (1.0, "Graphs"), (2.0, "Proofs")])
    tl, tip = window.controller.timeline, window.seek_tip
    assert tl.track_gaps(tl._margin(), tl._span(), tl.height() / 2, 4) != []
    window._on_chapters_changed(False)
    assert tl.track_gaps(tl._margin(), tl._span(), tl.height() / 2, 4) == []
    tl.hover_moved.emit(1.2, x_on_bar(window, 1.2))
    assert (tip.text, tip.detail) == ("0:01", "")
    window._on_chapters_changed(True)
    tl.hover_moved.emit(1.2, x_on_bar(window, 1.2))
    assert tip.text == "Graphs"
    tl.hover_left.emit()


def test_resizing_the_window_closes_the_panel(window, video, qapp, pump):
    window.toggle_bookmark_panel()
    assert window.bookmark_panel.isVisible()
    window.resize(window.width() + 120, window.height())
    pump(lambda: not window.bookmark_panel.isVisible(), timeout=2)
    assert not window.bookmark_panel.isVisible()


def test_a_video_with_no_chapters_and_no_bookmarks_has_no_marks(window, video, pump):
    tl = window.controller.timeline
    assert tl._bookmarks == [] and tl._chapters == [] and window.chapters == []


def test_after_a_click_in_the_panel_the_player_keys_still_work_and_still_do_after_it_closes(window, video, pills, monkeypatch, qapp, pump):
    """Final review: the click gave the panel's scroll area the focus, which swallowed the arrow keys (even once closed)."""
    for t in (0.7, 1.8, 2.9):
        add_at(window, t)
    window.toggle_bookmark_panel()
    pump(None, timeout=0.2)
    seeks = []
    monkeypatch.setattr(window, "seek_relative", lambda s: seeks.append(s))
    row = window.bookmark_panel.findChildren(_BookmarkRow)[1]
    QTest.mouseClick(row, Qt.LeftButton, Qt.NoModifier, row.rect().center())
    pump(None, timeout=0.2)
    window._time_pos = 0.0
    pills.clear()
    QTest.keyClick(qapp.focusWidget() or window, Qt.Key_Right, ALT)
    assert pills and pills[-1][0] == "북마크", "Alt+Right still jumps with the panel open"
    QTest.keyClick(qapp.focusWidget() or window, Qt.Key_Left)
    assert seeks == [-5.0], "and the plain arrow still seeks"
    QTest.keyClick(qapp.focusWidget() or window, Qt.Key_Escape)
    assert not window.bookmark_panel.isVisible()
    pump(None, timeout=0.1)
    QTest.keyClick(qapp.focusWidget() or window, Qt.Key_Right)
    assert seeks == [-5.0, 5.0], "closed: the arrows reach the player again"


def test_a_real_file_with_chapters_shows_them_on_the_bar_and_in_the_pill(window, pump, pills):
    from pathlib import Path
    path = str(Path(__file__).parent / "assets" / "chapters.mkv")
    window.load_media_file(path)
    assert pump(lambda: window.chapters and window.controller.timeline._duration > 0, timeout=10)
    window.engine.pause()
    assert window.chapters == [(0.0, "Intro"), (1.0, "Middle"), (2.0, "End")]
    tl = window.controller.timeline
    assert tl._chapters == [0.0, 1.0, 2.0]
    assert len(tl.track_gaps(tl._margin(), tl._span(), tl.height() / 2, 4)) == 2, "a gap at 1 s and at 2 s, none at 0"
    tl.hover_moved.emit(1.4, x_on_bar(window, 1.4))
    assert (window.seek_tip.text, window.seek_tip.detail) == ("Middle", "0:01")
    tl.hover_left.emit()
