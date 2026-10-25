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
