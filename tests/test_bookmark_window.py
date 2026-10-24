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
