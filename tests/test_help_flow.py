"""HelpFlow: when the help opens, which layout it takes, and the places that close or re-place it."""
from ui.help_panel import HelpPanel


def test_nothing_is_created_before_the_first_open(window):
    assert window.help._panel is None
    assert not window.help.is_open()


def test_toggle_opens_and_closes(window):
    window.help.toggle()
    assert window.help.is_open() and window.help._panel.isVisible()
    window.help.toggle()
    assert not window.help.is_open() and not window.help._panel.isVisible()


def test_the_home_screen_gets_the_centred_layout_even_in_the_default_window(window):
    assert (window.width(), window.height()) == (1060, 640)
    window.help.open()
    assert window.help.layout_kind() == HelpPanel.CENTERED == window.help._panel.kind
    assert window.help.is_modal()
    panel = window.help._panel
    assert window.central_widget.rect().contains(panel.geometry())


def test_a_loaded_video_gets_the_drawer_and_keeps_playing(window, sample_video, pump):
    window.load_media_file(sample_video)
    assert pump(lambda: window.engine.is_playing(), timeout=5)
    window.help.open()
    assert window.help._panel.kind == HelpPanel.DRAWER
    assert not window.help.is_modal()
    pump(None, timeout=0.3)
    assert window.engine.is_playing(), "opening the help does not touch playback"


def test_a_small_window_gets_the_drawer_on_the_home_screen(window, pump):
    window.resize(640, 380)
    pump(None, timeout=0.2)
    window.help.open()
    assert window.help._panel.kind == HelpPanel.DRAWER
    assert window.central_widget.rect().contains(window.help._panel.geometry())


def test_opening_a_video_closes_the_help_and_so_does_a_file_problem(window, sample_video, pump):
    window.help.open()
    window.load_media_file(sample_video)
    assert not window.help.is_open()
    window.help.open()
    assert window.help.is_open()
    window._show_file_problem(sample_video, "gone")
    assert not window.help.is_open()


def test_a_resize_keeps_it_open_and_inside_the_window(window, pump):
    window.help.open()
    window.resize(800, 520)
    pump(None, timeout=0.2)
    assert window.help.is_open()
    assert window.central_widget.rect().contains(window.help._panel.geometry())
    window.resize(640, 380)
    pump(None, timeout=0.2)
    assert window.help.is_open() and window.central_widget.rect().contains(window.help._panel.geometry())
    assert window.help._panel.kind == HelpPanel.DRAWER, "re-chosen for the new size"


def test_the_title_bar_button_toggles_it_once(window):
    window.title_bar.help_clicked.emit()
    assert window.help.is_open()
    window.title_bar.help_clicked.emit()
    assert not window.help.is_open(), "exactly one toggle per click (two would leave it open)"


# --- the review's findings (real event dispatch, not direct calls) ----------------------------------------------------

def test_a_double_click_on_the_dim_closes_the_help_and_does_not_go_full_screen(window, monkeypatch, pump):
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtTest import QTest
    calls = []
    monkeypatch.setattr(window, "toggle_fullscreen", lambda: calls.append(1))
    window.help.open()
    assert window.help.is_modal()
    QTest.mouseDClick(window.windowHandle(), Qt.LeftButton, Qt.NoModifier, QPoint(30, 300))
    pump(None, timeout=0.2)
    assert not window.help.is_open()
    assert calls == [], "the second click of the double click must not reach the video area"
    pump(lambda: not window.help._panel._dim.isVisible(), timeout=2)
    assert not window.help._panel._dim.isVisible(), "the dim only absorbs the double click, then goes"


def test_escape_reaches_the_help_even_when_a_popup_holds_the_focus(window, sample_video, pump):
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication
    window.load_media_file(sample_video)
    assert pump(lambda: window._duration > 0, timeout=5)
    window.toggle_bookmark_panel()
    assert window.bookmark_panel.isVisible()
    window.help.open()
    QTest.keyClick(QApplication.focusWidget() or window, Qt.Key_Escape)
    assert not window.help.is_open(), "the first Esc closes the help, whoever has the focus"
    assert window.bookmark_panel.isVisible()


def test_the_drawer_leaves_the_control_strip_free(window, sample_video, pump):
    window.load_media_file(sample_video)
    assert pump(lambda: window._duration > 0, timeout=5)
    window.help.open()
    panel = window.help._panel
    c = window.controller
    assert panel.geometry().bottom() < c.geometry().bottom() - c.CONTROLS_HEIGHT + 1, "it ends above the controls"


def test_popups_and_the_info_panel_stay_above_the_drawer(window, sample_video, pump):
    window.load_media_file(sample_video)
    assert pump(lambda: window._duration > 0, timeout=5)
    window.help.open()
    window.info_panel.show()
    window.toggle_bookmark_panel()
    window._reposition_floating_widgets()
    kids = window.central_widget.children()
    help_at = kids.index(window.help._panel)
    assert kids.index(window.info_panel) > help_at
    assert kids.index(window.bookmark_panel) > help_at


def test_the_centred_dim_and_panel_are_above_the_title_bar_and_the_update_card(window):
    window.help.open()
    window._reposition_floating_widgets()
    kids = window.central_widget.children()
    dim = kids.index(window.help._panel._dim)
    assert dim > kids.index(window.title_bar) and dim > kids.index(window.update_card)
    assert kids.index(window.help._panel) > dim
