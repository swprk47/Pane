"""MainWindow: frame, render surface, empty/loaded states, PIP, shortcuts, click handling."""
import re
from pathlib import Path

import pytest
from PySide6.QtCore import Qt, QPoint
from PySide6.QtGui import QContextMenuEvent
from PySide6.QtTest import QTest

from ui.mpv_gl import MpvGLWidget

UI_DIR = Path(__file__).resolve().parent.parent / "ui"


# --- structure -------------------------------------------------------------

def test_viewport_is_the_render_surface(window):
    assert isinstance(window.viewport, MpvGLWidget)
    assert window.viewport._mpv is window.engine.mpv


def test_render_does_not_block_the_gui_thread():
    """mpv's render() blocks until the frame's display time by default, which kept the GUI
    thread waiting ~21 ms per 30 fps frame (measured with tools/flicker_probe.py). We render
    without blocking. A timing test could not tell the two apart on the short sample clip, so
    this checks the setting itself."""
    assert MpvGLWidget.BLOCK_FOR_TARGET_TIME is False


def test_theme_survives_the_acrylic_call(window):
    """Regression: pywinstyles.apply_style() replaces the window stylesheet with
    'background-color: transparent;', which wiped the theme and left the title bar
    and viewport alpha 0 (clicks fell through to the desktop)."""
    qss = window.styleSheet()
    assert len(qss) > 1000, f"theme stylesheet was replaced: {qss!r}"
    assert "GlassTitleBar" in qss


def test_title_bar_floats_over_a_video_that_fills_the_window(window, qapp):
    """The bar is an overlay (no layout space), the video fills the whole window, and the bar paints no
    background of its own, so the window area under it is the opaque viewport (no click-through)."""
    qapp.processEvents()
    central = window.central_widget
    assert window.viewport.geometry() == central.rect()
    assert window.title_bar.geometry().top() == 0 and window.title_bar.height() == window.title_bar.HEIGHT
    assert window.title_bar.width() == central.width()
    assert not window.title_bar.testAttribute(Qt.WA_StyledBackground)
    assert window.title_bar.parentWidget() is central


def test_no_emoji_left_in_ui_source():
    """Emoji were replaced by SVG line icons; keep it that way."""
    emoji = re.compile("[\U0001F000-\U0001FFFF☀-➿⏩-⏳⛶⭐️]")
    offenders = []
    for path in UI_DIR.glob("*.py"):
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            # ✓ / ✕ / ▲ / ▼ are plain text glyphs used on purpose
            stripped = line.replace("✓", "").replace("✕", "")
            if emoji.search(stripped):
                offenders.append(f"{path.name}:{n}: {line.strip()[:70]}")
    assert not offenders, "\n".join(offenders)


# --- empty vs loaded -------------------------------------------------------

def test_empty_state(window):
    assert window.viewport.notice_widget.isVisible()
    assert not window.controller.isVisible(), "controls must stay hidden without media"
    assert not window.top_scrim.isVisible()
    assert not window.center_badge.isVisible(), "no pause symbol over the start screen"
    assert not window.viewport.start_screen._logo.isNull()


def test_loading_a_file_switches_to_player_state(window, sample_video, pump):
    window.load_media_file(sample_video)
    assert not window.viewport.notice_widget.isVisible()
    assert window.controller.isVisible()
    assert window.top_scrim.isVisible()
    assert "sample.mp4" in window.top_scrim._title        # the file name is shown on the video, not in the title bar
    assert not hasattr(window.title_bar, "file_label")
    assert pump(lambda: window.engine._time_pos > 0.2)
    assert sample_video in window.app_settings.get_recent_files() \
        if hasattr(window.app_settings, "get_recent_files") else True


def test_missing_file_is_ignored(window, tmp_path):
    window.load_media_file(str(tmp_path / "nope.mp4"))
    assert window.viewport.notice_widget.isVisible()
    assert window._current_file is None


def test_overlay_geometry_covers_the_video_area(window, sample_video, pump):
    window.load_media_file(sample_video)
    pump(timeout=0.3)
    vp = window.viewport.geometry()
    c = window.controller.geometry()
    assert c.width() == vp.width() and c.bottom() == vp.bottom()
    assert window.top_scrim.geometry().top() == vp.top()


def test_paused_state_shows_center_badge(window, sample_video, pump):
    window.load_media_file(sample_video)
    assert pump(lambda: window.engine._time_pos > 0.2)
    assert not window.center_badge.isVisible()
    window.engine.pause()
    assert pump(lambda: window.center_badge.isVisible())
    window.engine.play()
    assert pump(lambda: not window.center_badge.isVisible())


def test_mini_progress_shows_only_while_controls_hidden(window, sample_video, pump, monkeypatch):
    monkeypatch.setattr(window.controller, "_mouse_over_controls", lambda: False)   # not the real cursor
    window.load_media_file(sample_video)
    pump(timeout=0.3)
    assert not window.mini_progress.isVisible()
    window.controller.hold_visible = None
    window.controller.volume_popup.hide()
    window.controller._fade_out()
    assert pump(lambda: window.mini_progress.isVisible(), timeout=1.5)


# --- PIP / fullscreen ------------------------------------------------------

def test_pip_roundtrip_keeps_badge_style(window, qapp, pump):
    """Regression: leaving PIP cleared the badge's own stylesheet, so it came back
    unstyled."""
    badge = window.title_bar.btn_pip
    before_qss = badge.styleSheet()
    before_img = badge.grab().toImage()
    assert before_qss

    window.toggle_pip_mode()
    pump(timeout=0.5)
    assert window._is_pip and badge.property("active") == "true"

    window.toggle_pip_mode()
    pump(timeout=0.5)
    assert not window._is_pip
    assert badge.styleSheet() == before_qss
    assert badge.grab().toImage() == before_img, "badge looks different after leaving PIP"


def test_pip_does_not_recreate_the_native_window(window, qapp, pump):
    """Regression: toggling Qt's WindowStaysOnTopHint recreated the native window, which blanked
    the video for ~60 ms on every PIP toggle (measured with tools/flicker_probe.py)."""
    from PySide6.QtCore import QEvent, QObject

    class Watch(QObject):
        def __init__(self):
            super().__init__()
            self.recreated = 0

        def eventFilter(self, obj, event):
            if event.type() == QEvent.WinIdChange:
                self.recreated += 1
            return False

    watch = Watch()
    window.installEventFilter(watch)
    hwnd = int(window.winId())
    assert not window.is_always_on_top()

    window.toggle_pip_mode()
    assert pump(lambda: window.is_always_on_top(), timeout=2.0)
    window.toggle_pip_mode()
    assert pump(lambda: not window.is_always_on_top(), timeout=2.0)

    assert watch.recreated == 0
    assert int(window.winId()) == hwnd


def test_render_context_survives_window_recreation(window, sample_video, pump):
    window.load_media_file(sample_video)
    pump(timeout=0.4)
    window.toggle_pip_mode()
    assert pump(lambda: window.viewport._ctx is not None, timeout=2.0)
    window.toggle_pip_mode()
    assert pump(lambda: window.viewport._ctx is not None, timeout=2.0)


def test_fullscreen_toggle(window, pump):
    window.toggle_fullscreen()
    pump(timeout=0.4)
    assert window.isFullScreen() and not window.title_bar.isVisible()
    window.toggle_fullscreen()
    pump(timeout=0.4)
    assert not window.isFullScreen() and window.title_bar.isVisible()


# --- keyboard --------------------------------------------------------------

def test_speed_shortcuts(window, pump):
    key = lambda k, mod=Qt.NoModifier: QTest.keyClick(window, k, mod)
    key(Qt.Key_BracketRight)
    assert window.engine.get_speed() == pytest.approx(1.1)
    key(Qt.Key_BracketRight, Qt.ShiftModifier)
    assert window.engine.get_speed() == pytest.approx(1.15)
    key(Qt.Key_BracketLeft)
    assert window.engine.get_speed() == pytest.approx(1.05)
    key(Qt.Key_Backslash)
    assert window.engine.get_speed() == 1.0
    key(Qt.Key_BracketRight)
    key(Qt.Key_Backspace)
    assert window.engine.get_speed() == 1.0


def test_space_toggles_playback(window, sample_video, pump):
    window.load_media_file(sample_video)
    pump(lambda: window.engine._time_pos > 0.2)
    QTest.keyClick(window, Qt.Key_Space)
    assert pump(lambda: not window.engine.is_playing())
    QTest.keyClick(window, Qt.Key_Space)
    assert pump(lambda: window.engine.is_playing())


def test_seek_and_mute_shortcuts(window, sample_video, pump):
    window.load_media_file(sample_video)
    window.engine.set_speed(0.5)
    pump(lambda: window.engine._time_pos > 0.2)
    start = window.engine._time_pos
    QTest.keyClick(window, Qt.Key_Right)                       # +5 s, clamped by the 3 s file
    assert pump(lambda: window.engine._time_pos > start + 0.5)
    QTest.keyClick(window, Qt.Key_M)
    assert window.engine.mpv.mute is True
    QTest.keyClick(window, Qt.Key_M)
    assert window.engine.mpv.mute is False


def test_p_key_toggles_pip(window):
    QTest.keyClick(window, Qt.Key_P)
    assert window._is_pip is True
    QTest.keyClick(window, Qt.Key_P)
    assert window._is_pip is False


# --- mouse handling (signal level) -----------------------------------------

def test_single_click_toggles_play_after_a_short_wait(window, sample_video, pump):
    window.load_media_file(sample_video)
    pump(lambda: window.engine._time_pos > 0.2)
    window.viewport.clicked.emit()
    assert pump(lambda: not window.engine.is_playing(), timeout=1.0)
    window.viewport.clicked.emit()
    assert pump(lambda: window.engine.is_playing(), timeout=1.0)


def test_double_click_goes_fullscreen_without_toggling_play(window, sample_video, pump):
    window.load_media_file(sample_video)
    pump(lambda: window.engine._time_pos > 0.2)
    window.viewport.clicked.emit()                              # first click of the pair
    window.viewport.double_clicked.emit()
    pump(timeout=0.6)
    assert window.isFullScreen()
    assert window.engine.is_playing(), "the pending single-click toggle must be cancelled"
    window.toggle_fullscreen()


def test_click_on_the_start_screen_does_not_open_the_file_dialog(window, monkeypatch):
    """Only the "영상 열기" button (and Ctrl+O / the menu) open the dialog; the empty screen is for dragging the window."""
    opened = []
    monkeypatch.setattr(window, "_open_file_dialog", lambda: opened.append(1))
    window._on_viewport_clicked()
    assert opened == []
    window.viewport.start_screen.btn_open.click()
    assert opened == [1]


def test_context_menu_opens_through_one_path(window):
    """Regression: the menu used to open from both mousePress and contextMenuEvent."""
    calls = []
    window.viewport.context_menu_requested.disconnect()
    window.viewport.context_menu_requested.connect(lambda p: calls.append(p))
    ev = QContextMenuEvent(QContextMenuEvent.Mouse, QPoint(50, 50), window.viewport.mapToGlobal(QPoint(50, 50)))
    window.viewport.contextMenuEvent(ev)
    assert len(calls) == 1


# --- end of playback -------------------------------------------------------

def test_playback_finished_osd(window, sample_video, pump):
    """Regression: file_ended never fired with keep_open=yes, so this OSD never showed."""
    window.load_media_file(sample_video)
    window.engine.set_speed(4.0)
    assert pump(lambda: window.osd.text_label.text() == "재생 완료", timeout=6.0)


def test_paused_seek_updates_position(window, sample_video, pump):
    window.load_media_file(sample_video)
    pump(lambda: window.engine._time_pos > 0.3)
    window.engine.pause()
    pump(timeout=0.3)
    seen = []
    window.engine.time_pos_changed.connect(seen.append)
    window.engine.seek(2.0, "absolute")
    # Record every update instead of polling: with this 3 s sample mpv reports 2.0 for a moment and then
    # falls back to 0.0, so a poll could miss it depending on timing (the test used to pass by luck).
    assert pump(lambda: any(abs(v - 2.0) < 0.2 for v in seen), timeout=2.0), \
        f"time_pos never reached 2.0, saw {seen}"


# --- title bar: drag vs double-click ---------------------------------------

@pytest.fixture
def title_drag(window, monkeypatch, pump):
    """Records native window-drag starts instead of entering the system move loop."""
    import ui.title_bar as tb
    calls = []
    monkeypatch.setattr(tb, "native_start_window_drag", lambda hwnd: calls.append(hwnd) or True)
    pump(timeout=0.2)
    return calls


def _empty_title_spot(window):
    return QPoint(window.title_bar.width() // 2, window.title_bar.height() // 2)


def test_title_bar_click_does_not_start_a_drag(window, title_drag):
    tb, pos = window.title_bar, _empty_title_spot(window)
    QTest.mousePress(tb, Qt.LeftButton, Qt.NoModifier, pos)
    QTest.mouseRelease(tb, Qt.LeftButton, Qt.NoModifier, pos)
    assert title_drag == []


def test_title_bar_small_jitter_does_not_start_a_drag(window, title_drag):
    tb, pos = window.title_bar, _empty_title_spot(window)
    QTest.mousePress(tb, Qt.LeftButton, Qt.NoModifier, pos)
    QTest.mouseMove(tb, pos + QPoint(2, 1))
    QTest.mouseRelease(tb, Qt.LeftButton, Qt.NoModifier, pos + QPoint(2, 1))
    assert title_drag == []


def test_title_bar_drag_starts_once_after_the_threshold(window, title_drag):
    from PySide6.QtWidgets import QApplication
    tb, pos = window.title_bar, _empty_title_spot(window)
    far = QApplication.startDragDistance() + 8
    QTest.mousePress(tb, Qt.LeftButton, Qt.NoModifier, pos)
    QTest.mouseMove(tb, pos + QPoint(far, 0))
    QTest.mouseMove(tb, pos + QPoint(far + 10, 0))
    assert len(title_drag) == 1, "the move loop must start exactly once per drag"
    QTest.mouseRelease(tb, Qt.LeftButton, Qt.NoModifier, pos + QPoint(far + 10, 0))


def test_title_bar_double_click_toggles_maximize_without_dragging(window, title_drag, pump):
    """Regression: the drag used to start on the first press, which swallowed the button-up and
    stopped the double-click from ever arriving."""
    tb, pos = window.title_bar, _empty_title_spot(window)
    assert not window.isMaximized()
    QTest.mouseDClick(tb, Qt.LeftButton, Qt.NoModifier, pos)
    pump(timeout=0.4)
    assert window.isMaximized()
    assert title_drag == []
    QTest.mouseDClick(tb, Qt.LeftButton, Qt.NoModifier, pos)
    pump(timeout=0.4)
    assert not window.isMaximized()


def test_title_bar_does_not_drag_a_maximized_window(window, title_drag, pump):
    from PySide6.QtWidgets import QApplication
    window.showMaximized()
    pump(timeout=0.4)
    tb, pos = window.title_bar, _empty_title_spot(window)
    QTest.mousePress(tb, Qt.LeftButton, Qt.NoModifier, pos)
    QTest.mouseMove(tb, pos + QPoint(QApplication.startDragDistance() + 20, 0))
    QTest.mouseRelease(tb, Qt.LeftButton, Qt.NoModifier, pos)
    assert title_drag == []
    window.showNormal()


def test_single_click_toggles_at_once(window, sample_video, pump):
    """The click used to wait 260 ms to rule out a double-click; now it reacts immediately."""
    window.load_media_file(sample_video)
    assert pump(lambda: window.engine._time_pos > 0.2, timeout=3.0)
    assert window.engine.is_playing()
    window.viewport.clicked.emit()
    assert not window.engine.is_playing(), "the click must pause right away, not after a delay"
    window.viewport.clicked.emit()
    assert window.engine.is_playing()


def test_double_click_undoes_the_first_click_toggle_only_within_the_window(window, sample_video, pump):
    window.load_media_file(sample_video)
    assert pump(lambda: window.engine._time_pos > 0.2, timeout=3.0)
    window.viewport.clicked.emit()                       # toggles now (paused)
    assert window._click_undo_armed
    window._disarm_click_undo()                          # the double-click window passed
    window.viewport.double_clicked.emit()
    assert not window.engine.is_playing(), "late double-click must not undo anything"
    window.toggle_fullscreen()


def test_title_bar_shows_only_the_app_name(window, sample_video):
    """The file name already sits on the video's top scrim, so the bar no longer repeats it."""
    labels = [w.text() for w in window.title_bar.findChildren(type(window.title_bar.title_label))]
    window.load_media_file(sample_video)
    after = [w.text() for w in window.title_bar.findChildren(type(window.title_bar.title_label))]
    assert after == labels == ["Pane"]


# --- arrow keys keep working after the sliders were used -------------------------

def test_clicking_a_slider_does_not_take_the_arrow_keys(window, sample_video, pump, qapp):
    window.load_media_file(sample_video)
    assert pump(lambda: window.engine.get_media_info().get("width"), timeout=5)
    window.activateWindow()
    sliders = (window.controller.timeline, window.controller.vol_slider, window.speed_popup.slider)
    window.speed_popup.show()                                     # (so that its slider can be clicked)
    pump(timeout=0.2)
    for slider in sliders:
        QTest.mouseClick(slider, Qt.LeftButton)
        pump(timeout=0.1)
        assert qapp.focusWidget() is not slider, type(slider).__name__
    window.speed_popup.hide()
    window.engine.set_volume(50)
    QTest.keyClick(qapp.focusWidget() or window, Qt.Key_Up)       # a real key press goes to the focus widget
    assert window.engine.get_volume() == 55.0


# --- closing -------------------------------------------------------------------

def test_x_button_hides_the_window_before_the_slow_cleanup(qapp, sample_video, pump):
    """Stopping mpv and freeing the render context takes ~0.4 s while a video plays; the window used to stay on
    screen, frozen, until that was done."""
    from ui.main_window import MainWindow
    w = MainWindow()
    w.show()
    w.load_media_file(sample_video)
    pump(timeout=0.5)
    seen = []
    real_terminate = w.engine.terminate

    def terminate():
        seen.append(w.isVisible())
        real_terminate()

    w.engine.terminate = terminate
    w.title_bar.btn_close.click()
    assert seen == [False], "mpv was stopped once, after the window was gone"
