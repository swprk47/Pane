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


def test_theme_survives_the_acrylic_call(window):
    """Regression: pywinstyles.apply_style() replaces the window stylesheet with
    'background-color: transparent;', which wiped the theme and left the title bar
    and viewport alpha 0 (clicks fell through to the desktop)."""
    qss = window.styleSheet()
    assert len(qss) > 1000, f"theme stylesheet was replaced: {qss!r}"
    assert "GlassTitleBar" in qss


def test_title_bar_paints_its_background(window):
    assert window.title_bar.testAttribute(Qt.WA_StyledBackground)


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
    assert not window.viewport.lbl_icon.pixmap().isNull()


def test_loading_a_file_switches_to_player_state(window, sample_video, pump):
    window.load_media_file(sample_video)
    assert not window.viewport.notice_widget.isVisible()
    assert window.controller.isVisible()
    assert window.top_scrim.isVisible()
    assert "sample.mp4" in window.title_bar.file_label.text()
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


def test_mini_progress_shows_only_while_controls_hidden(window, sample_video, pump):
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


def test_click_on_empty_viewport_opens_file_dialog(window, monkeypatch):
    opened = []
    monkeypatch.setattr(window, "_open_file_dialog", lambda: opened.append(1))
    window._on_viewport_clicked()
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
    window.engine.seek(2.0, "absolute")
    assert pump(lambda: abs(window.engine._time_pos - 2.0) < 0.2, timeout=2.0), \
        f"time_pos stayed at {window.engine._time_pos}"
