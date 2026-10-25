"""The keys of the help: ? toggles it, Esc closes it before anything else, the centred one is modal, the drawer is not."""
import pytest
from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QLineEdit

from ui.bookmark_panel import _BookmarkRow


def press(window, key, modifiers=Qt.NoModifier, text=""):
    window.keyPressEvent(QKeyEvent(QEvent.KeyPress, key, modifiers, text))


@pytest.fixture
def video(window, sample_video, pump):
    window.load_media_file(sample_video)
    assert pump(lambda: window._duration > 0, timeout=5)
    return sample_video


def test_question_mark_toggles_the_help(window):
    QTest.keyClick(window, Qt.Key_Question, Qt.ShiftModifier)
    assert window.help.is_open()
    QTest.keyClick(window, Qt.Key_Question, Qt.ShiftModifier)
    assert not window.help.is_open()
    QTest.keyClick(window, Qt.Key_Slash, Qt.ShiftModifier)
    assert window.help.is_open()
    QTest.keyClick(window, Qt.Key_Slash, Qt.ShiftModifier)
    assert not window.help.is_open()


def test_a_plain_slash_or_a_ctrl_question_mark_is_not_the_help(window):
    press(window, Qt.Key_Slash)
    press(window, Qt.Key_Question, Qt.ControlModifier)
    press(window, Qt.Key_Question, Qt.AltModifier)
    assert not window.help.is_open()


def test_a_question_mark_typed_in_the_rename_field_is_a_character(window, video):
    window._time_pos = 0.3
    window.add_bookmark()
    window.toggle_bookmark_panel()
    window.bookmark_panel.findChildren(_BookmarkRow)[0].edit_button.click()
    field = window.bookmark_panel.findChildren(QLineEdit)[0]
    assert window.bookmark_panel.is_editing
    field.clear()
    QTest.keyClick(field, Qt.Key_Question, Qt.ShiftModifier, 0)
    assert field.text() == "?" and not window.help.is_open()
    press(window, Qt.Key_Question, Qt.ShiftModifier, "?")          # (what a key the field left unhandled does)
    assert not window.help.is_open(), "the guard for a name being typed is before the help key"


def test_escape_closes_the_help_before_leaving_full_screen(window, video, qapp):
    window.toggle_fullscreen()
    try:
        assert window.isFullScreen()
        window.help.open()
        press(window, Qt.Key_Escape)
        assert not window.help.is_open() and window.isFullScreen(), "the first Esc closes only the help"
        press(window, Qt.Key_Escape)
        assert not window.isFullScreen()
    finally:
        if window.isFullScreen():
            window.toggle_fullscreen()


def test_escape_closes_the_help_before_the_bookmark_list(window, video):
    window.toggle_bookmark_panel()
    window.help.open()
    press(window, Qt.Key_Escape)
    assert not window.help.is_open() and window.bookmark_panel.isVisible()
    press(window, Qt.Key_Escape)
    assert not window.bookmark_panel.isVisible()


def test_the_centred_help_swallows_other_keys(window, monkeypatch):
    calls = []
    monkeypatch.setattr(window, "toggle_mute", lambda *a, **k: calls.append("mute"))
    monkeypatch.setattr(window.engine, "toggle_play", lambda: calls.append("play"))
    monkeypatch.setattr(window, "toggle_fullscreen", lambda: calls.append("full"))
    window.help.open()
    assert window.help.is_modal()
    for key in (Qt.Key_M, Qt.Key_Space, Qt.Key_F, Qt.Key_Return, Qt.Key_P, Qt.Key_B):
        press(window, key)
    assert calls == [] and window.help.is_open()
    press(window, Qt.Key_Escape)
    assert not window.help.is_open() and calls == []
    window.help.open()
    press(window, Qt.Key_Question, Qt.ShiftModifier)
    assert not window.help.is_open(), "? closes it too"


def test_in_the_drawer_the_shortcuts_still_work(window, video, monkeypatch):
    calls = []
    monkeypatch.setattr(window, "toggle_mute", lambda *a, **k: calls.append("mute"))
    window.help.open()
    assert not window.help.is_modal()
    press(window, Qt.Key_M)
    assert calls == ["mute"] and window.help.is_open()


def test_the_router_checks_the_help_after_the_settings_panel(window):
    c = window.controller
    c._open_settings_dialog()
    assert c.settings_panel is not None
    window.help.open()
    press(window, Qt.Key_Escape)
    assert c.settings_panel is None or not c.settings_panel.isVisible(), "Esc went to the settings panel, as before"
    assert window.help.is_open(), "...and not to the help"
    window.help.close()
