"""GlassController: layout, state display, overlay behaviour, volume popup."""
import json

import pytest
from PySide6.QtWidgets import QWidget, QPushButton

from core.settings import open_settings
from ui.glass_controller import GlassController, DEFAULT_LAYOUT, LAYOUT_VERSION


@pytest.fixture
def host(qapp):
    h = QWidget()
    h.resize(1000, 600)
    h.show()
    yield h
    h.close()


@pytest.fixture
def controller(host, qapp):
    c = GlassController(host)
    c.setGeometry(0, 600 - c.STRIP_HEIGHT, 1000, c.STRIP_HEIGHT)
    c.set_media_loaded(True)
    c.show()
    qapp.processEvents()
    return c


def button(controller, tooltip_start):
    for b in controller.findChildren(QPushButton):
        if b.toolTip().startswith(tooltip_start):
            return b
    raise AssertionError(f"no button with tooltip {tooltip_start!r}")


# --- layout ----------------------------------------------------------------

def test_default_layout_puts_transport_in_the_center(controller):
    assert "play_pause" in controller.current_layout["center"]
    assert "seek_backward" in controller.current_layout["center"]
    assert "time_label" in controller.current_layout["left"]
    assert "volume" in controller.current_layout["right"]
    assert controller.current_layout == DEFAULT_LAYOUT


def test_play_button_is_centered(controller):
    p = controller.btn_play
    center = p.mapTo(controller, p.rect().center()).x()
    assert abs(center - controller.width() // 2) <= 3


def test_side_zones_have_equal_width(controller):
    assert controller.left_zone.width() == controller.right_zone.width()


def test_custom_layout_rebuilds_and_persists(host, qapp):
    c = GlassController(host)
    custom = {"left": ["play_pause", "time_label"], "center": ["speed_button"], "right": ["volume", "fullscreen"]}
    c._save_layout(custom)
    assert c.current_layout == custom
    assert hasattr(c, "btn_speed") and hasattr(c, "btn_mute")
    again = GlassController(host)
    assert again.current_layout == custom


def test_stale_saved_layout_is_reset_once(host):
    s = open_settings("ControllerLayout")
    s.setValue("button_layout", json.dumps({"left": ["play_pause"], "center": [], "right": []}))
    s.setValue("layout_version", LAYOUT_VERSION - 1)
    c = GlassController(host)
    assert c.current_layout == DEFAULT_LAYOUT


def test_compact_mode_hides_side_zones(controller):
    controller.set_compact(True)
    assert not controller.left_zone.isVisibleTo(controller)
    assert not controller.right_zone.isVisibleTo(controller)
    assert controller.btn_play.isVisibleTo(controller)
    controller.set_compact(False)
    assert controller.left_zone.isVisibleTo(controller)


# --- state display ---------------------------------------------------------

def test_time_label_format(controller):
    controller.set_duration(645.0)
    controller.set_time_pos(83.0)
    assert controller.lbl_time.text() == "01:23 / 10:45"
    controller.set_duration(7707.0)
    controller.set_time_pos(3723.0)
    assert controller.lbl_time.text() == "01:02:03 / 02:08:27"


def test_speed_display(controller):
    controller.set_speed_display(1.40)
    assert controller.btn_speed.text() == "1.40x"


def test_play_icon_switches_with_state(controller):
    controller.set_playback_state(False)
    paused_key = controller.btn_play.icon().cacheKey()
    controller.set_playback_state(True)
    playing_key = controller.btn_play.icon().cacheKey()
    assert paused_key != playing_key, "play and pause icons must differ"
    assert controller.btn_play.text() == ""          # icon-only (SVG), no glyph text


def test_mute_icon_switches(controller):
    controller.set_volume_display(50, is_muted=False)
    normal = controller.btn_mute.icon().cacheKey()
    controller.set_volume_display(50, is_muted=True)
    assert controller.btn_mute.icon().cacheKey() != normal


# --- signals ---------------------------------------------------------------

def test_transport_buttons_emit(controller):
    got = []
    controller.seek_forward_clicked.connect(lambda s: got.append(("fwd", s)))
    controller.seek_backward_clicked.connect(lambda s: got.append(("back", s)))
    controller.play_pause_clicked.connect(lambda: got.append("play"))
    button(controller, "5초 앞").click()
    button(controller, "5초 뒤").click()
    controller.btn_play.click()
    assert got == [("fwd", 5.0), ("back", 5.0), "play"]


def test_timeline_click_requests_seek(controller, qapp):
    controller.set_duration(100.0)
    got = []
    controller.seek_requested.connect(got.append)
    controller.timeline.seek_requested.emit(42.0)
    assert got == [42.0]


# --- volume popup ----------------------------------------------------------

def test_volume_popup_sync_and_signal(controller, qapp):
    got = []
    controller.volume_changed.connect(got.append)
    controller.set_volume_display(35)
    assert controller.vol_slider.value() == 35 and got == []        # sync must not echo
    controller.vol_slider.setValue(80)
    assert got == [80.0]


def test_timeline_thumb_is_a_single_white_circle(controller):
    """Regression: an accent dot with a translucent 3px border looked like two overlapping circles."""
    qss = controller.timeline.styleSheet()
    handle = qss[qss.index("QSlider::handle:horizontal {"):]
    handle = handle[:handle.index("}")]
    assert "#FFFFFF" in handle
    assert "border" not in handle.replace("border-radius", "")
    assert "width: 14px" in handle and "height: 14px" in handle


def test_volume_popup_is_slim(controller):
    """Thin track and small round thumb (the thick pill version was the old look)."""
    pop = controller.volume_popup
    assert pop.width() <= 40
    qss = pop.styleSheet()
    assert "width: 3px" in qss                       # 3 px track
    assert "height: 13px" in qss                     # 13 px round thumb
    assert "width: 8px" not in qss


def test_volume_popup_opens_above_mute_button(controller):
    controller.volume_popup.open_above(controller.btn_mute)
    pop = controller.volume_popup
    assert pop.isVisible()
    btn_top = controller.btn_mute.mapTo(pop.parentWidget(), controller.btn_mute.rect().topLeft()).y()
    assert pop.y() + pop.height() <= btn_top


# --- overlay behaviour -----------------------------------------------------

def test_hidden_until_media_is_loaded(host, qapp):
    c = GlassController(host)
    c.setGeometry(0, 370, 1000, 230)
    c.set_media_loaded(False)
    c.trigger_activity()
    assert not c.isVisible()
    c.set_media_loaded(True)
    assert c.isVisible()


def test_unloading_media_hides_controls(controller):
    controller.set_media_loaded(False)
    assert not controller.isVisible()


def test_visibility_signal(host, qapp):
    c = GlassController(host)
    c.setGeometry(0, 370, 1000, 230)
    seen = []
    c.visibility_changed.connect(seen.append)
    c.set_media_loaded(True)
    c.hide()
    assert seen == [True, False]


def test_fade_out_and_back(controller, pump):
    controller.set_playback_state(True)
    controller.volume_popup.hide()
    controller.hold_visible = None
    controller._fade_out()
    assert pump(lambda: not controller.isVisible(), timeout=1.5)
    controller.trigger_activity()
    assert controller.isVisible()


def test_hold_visible_blocks_auto_hide(controller, pump):
    controller.set_playback_state(True)
    controller.hold_visible = lambda: True
    controller._fade_out()
    pump(timeout=0.4)
    assert controller.isVisible() and controller.opacity_effect.opacity() > 0.9
    controller.autohide_timer.stop()


def test_opacity_signal_follows_fade(controller, pump):
    seen = []
    controller.opacity_changed.connect(seen.append)
    controller.set_playback_state(True)
    controller.hold_visible = None
    controller._fade_out()
    pump(lambda: seen and seen[-1] <= 0.01, timeout=1.5)
    assert seen and seen[-1] <= 0.01


def test_empty_area_clicks_go_to_forward_target(controller, qapp):
    from PySide6.QtCore import QPoint, Qt, QEvent
    from PySide6.QtGui import QMouseEvent
    seen = []

    class Target(QWidget):
        def mousePressEvent(self, e):
            seen.append("press")

    t = Target(controller.parentWidget())
    t.setGeometry(0, 0, 1000, 400)
    controller.forward_target = t
    pos = QPoint(500, 20)                                       # empty gradient area
    gpos = controller.mapToGlobal(pos)
    ev = QMouseEvent(QEvent.MouseButtonPress, pos, gpos, Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
    qapp.sendEvent(controller, ev)
    assert seen == ["press"]
