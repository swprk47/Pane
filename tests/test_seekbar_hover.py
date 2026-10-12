"""The time shown when the mouse is over the seek bar: the tip, the preview fill and its end marker."""
import pytest
from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
from PySide6.QtGui import QImage, QMouseEvent, QRegion
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QWidget

from core.media_info import format_clock
from ui.glass_slider import TRACK_HOVER
from ui.overlay import SeekTimeTip
from ui.timeline_slider import TimelineSlider


# --- the clock text ----------------------------------------------------------

@pytest.mark.parametrize("sec,expected", [
    (0, "0:00"), (5, "0:05"), (59.9, "0:59"), (156, "2:36"), (600, "10:00"),
    (3599, "59:59"), (3600, "1:00:00"), (3765, "1:02:45"), (-4, "0:00"), (None, "0:00"),
])
def test_format_clock(sec, expected):
    assert format_clock(sec) == expected


# --- the slider --------------------------------------------------------------

@pytest.fixture
def slider(qapp):
    host = QWidget()
    host.resize(800, 80)
    s = TimelineSlider(host)
    s.setGeometry(0, 20, 800, 26)
    s.set_duration(250.0)
    host.show()
    qapp.processEvents()
    yield s
    host.close()


def move_to(s, x):
    QApplication.sendEvent(s, QMouseEvent(QEvent.MouseMove, QPointF(x, s.height() / 2), Qt.NoButton, Qt.NoButton, Qt.NoModifier))


def at_ratio(s, r):
    return s._margin() + r * s._span()


def test_hovering_reports_the_time_under_the_pointer_and_where_it_is(slider):
    got = []
    slider.hover_moved.connect(lambda sec, x: got.append((sec, x)))
    move_to(slider, at_ratio(slider, 0.5))
    assert got and abs(got[-1][0] - 125.0) < 0.5
    assert abs(got[-1][1] - at_ratio(slider, 0.5)) < 1
    move_to(slider, 2)                                   # past the left end: clamped to the start
    assert got[-1][0] == 0.0


def test_leaving_the_bar_reports_it(slider):
    left = []
    slider.hover_left.connect(lambda: left.append(1))
    move_to(slider, 100)
    QApplication.sendEvent(slider, QEvent(QEvent.Leave))
    assert left


def test_nothing_is_reported_before_a_duration_is_known(slider):
    slider.set_duration(0)
    got = []
    slider.hover_moved.connect(lambda *a: got.append(a))
    move_to(slider, 100)
    assert got == []


def test_dragging_reports_the_time_it_would_seek_to(slider):
    got = []
    slider.hover_moved.connect(lambda sec, x: got.append(sec))
    QTest.mousePress(slider, Qt.LeftButton, Qt.NoModifier, QPoint(int(at_ratio(slider, 0.2)), 13))
    QApplication.sendEvent(slider, QMouseEvent(QEvent.MouseMove, QPointF(at_ratio(slider, 0.8), 13), Qt.NoButton, Qt.LeftButton, Qt.NoModifier))
    assert abs(got[-1] - 200.0) < 1.0
    QTest.mouseRelease(slider, Qt.LeftButton, Qt.NoModifier, QPoint(int(at_ratio(slider, 0.8)), 13))


def render(s) -> QImage:
    img = QImage(s.size(), QImage.Format_ARGB32_Premultiplied)
    img.fill(0)
    s.render(img, QPoint(), QRegion(), QWidget.RenderFlag(0))
    return img


def alpha(img, x, y):
    return img.pixelColor(int(x), int(y)).alpha()


def test_the_part_between_the_handle_and_the_pointer_is_lit_with_a_marker_at_its_end(slider):
    slider.set_time_pos(50.0)                            # handle at 20%
    slider._hover = 1.0
    move_to(slider, at_ratio(slider, 0.6))
    img = render(slider)
    cy = slider.height() / 2
    plain = alpha(img, at_ratio(slider, 0.9), cy)         # groove beyond the pointer
    lit = alpha(img, at_ratio(slider, 0.4), cy)           # between handle and pointer
    played = alpha(img, at_ratio(slider, 0.1), cy)
    assert plain < lit < played, (plain, lit, played)


def test_the_end_marker_is_exactly_as_thick_as_the_bar_is_when_hovered(slider):
    """It caps the lit part: no taller than the track (6.5 px), so nothing sticks out above or below."""
    slider.set_time_pos(50.0)
    slider._hover = 1.0
    x = at_ratio(slider, 0.6)
    move_to(slider, x)
    img = render(slider)
    cy = slider.height() / 2
    half = TRACK_HOVER / 2
    assert alpha(img, x, cy - half - 2) == 0, "above the bar: nothing"
    assert alpha(img, x, cy + half + 2) == 0, "below the bar: nothing"
    assert alpha(img, x, cy) >= 235, "the marker itself is solid"
    assert alpha(img, x, cy - half + 1) >= 235 and alpha(img, x, cy + half - 1) >= 235


def test_pointing_behind_the_handle_leaves_the_played_part_as_it_was(slider):
    slider.set_time_pos(150.0)                           # handle at 60%
    slider._hover = 1.0
    plain = render(slider)
    move_to(slider, at_ratio(slider, 0.2))
    pointed = render(slider)
    cy = slider.height() / 2
    for r in (0.1, 0.2, 0.4, 0.55):                      # before, at and after the pointer, all still played
        x = at_ratio(slider, r)
        assert pointed.pixelColor(int(x), int(cy)) == plain.pixelColor(int(x), int(cy)), r
    assert alpha(pointed, at_ratio(slider, 0.4), cy) >= 235


def test_no_preview_once_the_pointer_has_left(slider):
    slider.set_time_pos(50.0)
    slider._hover = 1.0
    move_to(slider, at_ratio(slider, 0.6))
    QApplication.sendEvent(slider, QEvent(QEvent.Leave))
    img = render(slider)
    cy = slider.height() / 2
    assert alpha(img, at_ratio(slider, 0.4), cy) == alpha(img, at_ratio(slider, 0.9), cy)


# --- the tip -----------------------------------------------------------------

def test_the_tip_is_hidden_until_used(qapp):
    host = QWidget()
    host.resize(600, 300)
    host.show()
    tip = SeekTimeTip(host)
    assert not tip.isVisible()
    host.close()


def test_the_tip_sits_centred_over_the_pointer_and_above_the_bar(qapp):
    host = QWidget()
    host.resize(600, 300)
    host.show()
    tip = SeekTimeTip(host)
    tip.show_at("2:36", 300, 200, host.rect())
    assert tip.isVisible() and tip.text == "2:36"
    assert abs(tip.geometry().center().x() - 300) <= 1
    assert tip.geometry().bottom() <= 200
    tip.hide_tip()
    assert not tip.isVisible()
    host.close()


def test_the_tip_stays_inside_the_picture_at_both_ends(qapp):
    host = QWidget()
    host.resize(600, 300)
    host.show()
    tip = SeekTimeTip(host)
    tip.show_at("0:00", 2, 200, host.rect())
    assert tip.geometry().left() >= 8
    tip.show_at("1:02:45", 598, 200, host.rect())
    assert tip.geometry().right() <= host.width() - 8
    host.close()


def test_the_tip_actually_paints_its_text_and_a_dark_pill(qapp):
    """(show_at alone never paints: a missing import in paintEvent was only found on a real screen.)"""
    host = QWidget()
    host.resize(600, 300)
    host.show()
    tip = SeekTimeTip(host)
    tip.show_at("2:36", 300, 200, host.rect())
    img = QImage(tip.size(), QImage.Format_ARGB32_Premultiplied)
    img.fill(0)
    tip.render(img, QPoint(), QRegion(), QWidget.RenderFlag(0))
    dark = img.pixelColor(img.width() // 2, 3)                          # inside the pill, above the text
    assert dark.alpha() > 120 and dark.red() < 40
    white = sum(1 for y in range(img.height()) for x in range(img.width())
                if img.pixelColor(x, y).red() > 200 and img.pixelColor(x, y).alpha() > 200)
    assert white > 20, "the time is drawn in white"
    host.close()


def test_the_tip_does_not_take_the_mouse(qapp):
    host = QWidget()
    tip = SeekTimeTip(host)
    assert tip.testAttribute(Qt.WA_TransparentForMouseEvents)


# --- in the player -----------------------------------------------------------

@pytest.fixture
def playing(window, sample_video, pump):
    window.load_media_file(sample_video)
    pump(lambda: window.engine.mpv._get_property("duration") is not None)
    window.controller.set_duration(window.engine.mpv._get_property("duration"))
    return window


def test_hovering_the_seek_bar_shows_the_time_above_it(playing):
    w = playing
    tl = w.controller.timeline
    move_to(tl, at_ratio(tl, 0.5))
    assert w.seek_tip.isVisible()
    assert w.seek_tip.text == format_clock(tl._duration * 0.5)
    bar_center_y = tl.mapTo(w.central_widget, QPoint(0, tl.height() // 2)).y()
    assert w.seek_tip.geometry().bottom() < bar_center_y


def test_leaving_the_bar_hides_the_tip(playing):
    w = playing
    tl = w.controller.timeline
    move_to(tl, at_ratio(tl, 0.5))
    QApplication.sendEvent(tl, QEvent(QEvent.Leave))
    assert not w.seek_tip.isVisible()


def test_the_tip_goes_when_the_controls_hide(playing):
    w = playing
    tl = w.controller.timeline
    move_to(tl, at_ratio(tl, 0.5))
    w.controller.visibility_changed.emit(False)
    assert not w.seek_tip.isVisible()


def test_loading_another_file_hides_the_tip(playing, sample_video):
    w = playing
    tl = w.controller.timeline
    move_to(tl, at_ratio(tl, 0.5))
    w.load_media_file(sample_video)
    assert not w.seek_tip.isVisible()


def test_the_tip_is_drawn_over_the_controls_also_after_the_window_lays_out_again(playing):
    w = playing
    tl = w.controller.timeline
    move_to(tl, at_ratio(tl, 0.5))
    w._reposition_floating_widgets()
    kids = w.central_widget.children()
    assert kids.index(w.seek_tip) > kids.index(w.controller)
