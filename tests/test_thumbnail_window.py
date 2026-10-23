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


# --- the hover wiring (Task 5) ---------------------------------------------------------------------
# Hovering is driven the way the seek bar reports it: timeline.hover_moved(seconds, x).
import time

import pytest
from PySide6.QtGui import QColor, QImage

from core.thumbnails import bucket_of


def solid(w=320, h=180):
    img = QImage(w, h, QImage.Format_RGB32)
    img.fill(QColor(200, 40, 40))
    return img


@pytest.fixture
def playing(window, sample_video, pump):
    """The window with sample.mp4 loaded and its length known; pictures are made with exact seeks (one keyframe)."""
    window.thumbnail_provider._exact = True
    window.load_media_file(sample_video)
    assert pump(lambda: window._duration > 0, timeout=10)
    return window


def hover(w, seconds, frac=0.5):
    tl = w.controller.timeline
    w.controller.timeline.hover_moved.emit(seconds, tl.width() * frac)


def test_hovering_shows_the_pill_and_then_the_picture_six_pixels_above_it(playing, pump):
    w = playing
    hover(w, 1.5)
    assert w.seek_tip.isVisible()
    assert pump(lambda: w.thumbnail_tip.isVisible(), timeout=10)
    tip, pill = w.thumbnail_tip, w.seek_tip
    assert tip.y() + tip.height() + 6 == pill.y(), "the picture's bottom edge sits 6 px above the pill"
    assert abs((tip.x() + tip.width() / 2) - (pill.x() + pill.width() / 2)) <= 1


def test_leaving_the_bar_hides_both(playing, pump):
    w = playing
    hover(w, 1.5)
    assert pump(lambda: w.thumbnail_tip.isVisible(), timeout=10)
    w.controller.timeline.hover_left.emit()
    assert not w.thumbnail_tip.isVisible() and not w.seek_tip.isVisible()


def test_with_thumbnails_off_only_the_pill_is_shown_and_no_second_mpv_exists(playing, pump):
    w = playing
    w._on_thumbnails_changed(False)
    hover(w, 1.5)
    pump(None, timeout=1.0)
    assert w.seek_tip.isVisible() and not w.thumbnail_tip.isVisible()
    assert w.thumbnail_provider.has_instance is False and w.thumbnail_provider._mpv is None


def test_stop_mode_shows_the_picture_only_after_the_pointer_rests(playing, pump):
    w = playing
    w.STOP_DELAY_MS = 80
    w._on_thumbnails_on_stop_changed(True)
    hover(w, 1.5)
    assert w.seek_tip.isVisible() and not w.thumbnail_tip.isVisible(), "moving: the time only"
    assert pump(lambda: w.thumbnail_tip.isVisible(), timeout=10), "resting: the picture appears"
    hover(w, 2.6, 0.7)                                      # the pointer moves on
    assert w.seek_tip.isVisible() and not w.thumbnail_tip.isVisible(), "only the picture is hidden"
    assert pump(lambda: w.thumbnail_tip.isVisible(), timeout=10)


def test_a_picture_for_a_place_the_pointer_left_is_not_shown(playing, pump):
    w = playing
    w.STOP_DELAY_MS = 60000                                 # nothing is requested by itself in this test
    w._on_thumbnails_on_stop_changed(True)
    hover(w, 2.5)
    here = bucket_of(w._thumb_seconds())                    # (the last second at most: sample.mp4 is only 3 s long)
    w._stop_timer.stop()                                    # (the pointer "rests": only the bucket can refuse the picture now)
    w.thumbnail_provider.thumbnail_ready.emit(w._current_file, here + 1, solid())
    assert not w.thumbnail_tip.isVisible(), "a picture for another 2 s step than the one under the pointer"
    w.thumbnail_provider.thumbnail_ready.emit(w._current_file, here, solid())
    assert w.thumbnail_tip.isVisible()
    w.thumbnail_provider.thumbnail_ready.emit("C:/other/file.mp4", here, solid())             # another file's picture
    w.controller.timeline.hover_left.emit()
    w.thumbnail_provider.thumbnail_ready.emit(w._current_file, here, solid())                 # the pointer is gone
    assert not w.thumbnail_tip.isVisible()


def test_nothing_is_requested_before_a_video_is_loaded_or_when_the_duration_is_unknown(window, sample_video, pump, monkeypatch):
    asked = []
    monkeypatch.setattr(window.thumbnail_provider, "request", lambda path, sec: asked.append((path, sec)))
    hover(window, 1.5)
    assert asked == [] and not window.thumbnail_tip.isVisible()
    window.load_media_file(sample_video)
    window._duration = 0.0                                  # (a stream: the length is not known)
    hover(window, 1.5)
    assert asked == [] and not window.thumbnail_tip.isVisible()


def test_opening_another_video_clears_the_picture_and_the_cache(playing, sample_video, pump):
    w = playing
    hover(w, 1.5)
    assert pump(lambda: w.thumbnail_tip.isVisible(), timeout=10)
    assert len(w.thumbnail_provider._cache) >= 1
    w.load_media_file(sample_video)
    assert not w.thumbnail_tip.isVisible() and len(w.thumbnail_provider._cache) == 0
    assert w.thumbnail_provider._path == sample_video


def test_closing_the_window_with_a_request_running_does_not_hang(qapp, sample_video, pump):
    from ui.main_window import MainWindow
    w = MainWindow()
    w.show()
    w.thumbnail_provider._exact = True
    w.load_media_file(sample_video)
    assert pump(lambda: w._duration > 0, timeout=10)
    hover(w, 1.5)                                           # a request is on its way
    t0 = time.time()
    w.close()
    qapp.processEvents()
    assert time.time() - t0 < 5 and w.thumbnail_provider.has_instance is False
    worker = w.thumbnail_provider._worker
    if worker is not None:
        worker.join(10)
        assert not worker.is_alive()
    assert w.thumbnail_provider._mpv is None, "no second mpv is left behind"


def test_the_switches_take_effect_at_once(playing, pump):
    w = playing
    hover(w, 1.5)
    assert pump(lambda: w.thumbnail_tip.isVisible(), timeout=10)
    w._on_thumbnails_changed(False)
    assert not w.thumbnail_tip.isVisible() and w.thumbnail_provider.has_instance is False
    w._on_thumbnails_changed(True)
    w._on_thumbnails_on_stop_changed(True)
    w.STOP_DELAY_MS = 60000
    hover(w, 2.6)
    assert w.seek_tip.isVisible() and not w.thumbnail_tip.isVisible(), "stop mode: no picture while moving"


# --- cleanup, stage B -----------------------------------------------------------------------------------

def test_the_end_of_the_bar_asks_for_the_last_second_not_the_very_end(playing, monkeypatch):
    w = playing
    asked = []
    monkeypatch.setattr(w.thumbnail_provider, "request", lambda path, sec: asked.append(sec))
    hover(w, w._duration)                                    # the pointer at the right end of the bar
    assert asked and asked[-1] <= w._duration - 1.0 + 1e-6 and asked[-1] >= 0.0


def test_the_length_of_the_previous_video_is_forgotten_when_another_is_opened(playing, sample_video, pump):
    w = playing
    assert w._duration > 0
    w.load_media_file(sample_video)
    assert w._duration == 0.0, "until the new video says how long it is, nothing may rely on the old length"
    assert pump(lambda: w._duration > 0, timeout=10), "and the new length does arrive"


# --- cleanup, stage C --------------------------------------------------------------------------------------

def test_a_resize_or_a_fullscreen_change_hides_the_pill_and_the_picture(playing, pump):
    """They were drawn for the bar where it was; after the window changed they would hang in the wrong place until the
    pointer moved again."""
    w = playing
    hover(w, 1.5)
    assert pump(lambda: w.thumbnail_tip.isVisible(), timeout=10) and w.seek_tip.isVisible()
    w.resize(w.width() + 140, w.height() + 60)
    pump(None, timeout=0.3)
    assert not w.seek_tip.isVisible() and not w.thumbnail_tip.isVisible(), "after a resize"
    hover(w, 1.5)
    assert pump(lambda: w.thumbnail_tip.isVisible(), timeout=10)
    w.toggle_fullscreen()
    pump(None, timeout=0.5)
    assert not w.seek_tip.isVisible() and not w.thumbnail_tip.isVisible(), "after entering fullscreen"
    w.toggle_fullscreen()
    pump(None, timeout=0.5)
