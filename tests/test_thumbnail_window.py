"""Seek-bar thumbnails in the main window: the settings (Task 1) and the hover wiring (Task 5)."""
from core.settings import AppSettings
from ui.settings_panel import PERFORMANCE_TAB


# --- the two settings and their switches (Task 1) ----------------------------------------------

def test_the_thumbnail_settings_default_to_following_on_and_stop_mode_off():
    s = AppSettings()
    assert s.get_thumbnails_enabled() is True and s.get_thumbnails_on_stop() is False
    s.set_thumbnails_enabled(False)
    s.set_thumbnails_on_stop(True)
    assert AppSettings().get_thumbnails_enabled() is False and AppSettings().get_thumbnails_on_stop() is True


def test_the_performance_tab_has_the_two_thumbnail_switches_and_they_save_at_once(window, qapp):
    window.controller._open_settings_dialog()
    panel = window.controller.settings_panel
    panel.set_tab(PERFORMANCE_TAB)
    assert panel.switch_thumbnails.checked is True and panel.switch_thumbnails_stop.checked is False
    panel.switch_thumbnails_stop.toggled.emit(True)
    assert AppSettings().get_thumbnails_on_stop() is True and window.thumbnails_on_stop is True
    panel.switch_thumbnails.toggled.emit(False)
    assert AppSettings().get_thumbnails_enabled() is False and window.thumbnails_on is False


def test_the_stop_switch_is_dimmed_and_inert_while_thumbnails_are_off(window, qapp):
    window.app_settings.set_thumbnails_enabled(False)
    window.controller.thumbnails_on = False
    window.controller._open_settings_dialog()
    panel = window.controller.settings_panel
    assert panel.row_thumbnails_stop.isEnabled() is False
    panel.switch_thumbnails.toggled.emit(True)
    assert panel.row_thumbnails_stop.isEnabled() is True
