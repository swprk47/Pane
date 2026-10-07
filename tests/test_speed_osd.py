"""Speed panel (presets, pin limit, per-chip delete) and the OSD badge."""
import pytest
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QEnterEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QWidget

from ui.osd_widget import GlassOSDWidget
from ui.speed_popup import SpeedPopup, PresetChip, DEFAULT_PRESETS, MAX_PRESETS


@pytest.fixture
def popup(qapp):
    host = QWidget()
    host.resize(700, 400)
    p = SpeedPopup(host)
    host.show()
    p.show()
    qapp.processEvents()
    yield p
    host.close()


def chips(popup):
    return [popup.preset_layout.itemAt(i).widget()
            for i in range(popup.preset_layout.count())
            if popup.preset_layout.itemAt(i).widget()]


# --- presets ---------------------------------------------------------------

def test_default_presets(popup):
    assert popup.presets == DEFAULT_PRESETS
    assert 1.4 not in popup.presets and 1.25 in popup.presets
    assert [c.speed for c in chips(popup)] == DEFAULT_PRESETS


def test_slider_snaps_to_005_and_emits(popup):
    emitted = []
    popup.speed_selected.connect(emitted.append)
    popup.slider.setValue(140)
    assert popup._current_speed == 1.40
    assert popup.lbl_speed_val.text() == "1.40x"
    assert emitted[-1] == 1.40
    popup.slider.setValue(143)               # not a multiple of 5 -> snaps
    assert popup._current_speed == 1.45


def test_pin_and_unpin(popup):
    popup.slider.setValue(140)
    assert popup._pin_current_speed() is True
    assert 1.4 in popup.presets
    assert [c.speed for c in chips(popup)] == sorted(popup.presets)
    popup._unpin_preset(1.4)
    assert 1.4 not in popup.presets


def test_pin_limit_is_six(popup):
    assert MAX_PRESETS == 6
    popup.slider.setValue(140)
    assert popup._pin_current_speed() is True          # 5 -> 6
    assert len(popup.presets) == MAX_PRESETS
    popup.slider.setValue(175)
    assert popup._pin_current_speed() is False         # refused
    assert 1.75 not in popup.presets and len(popup.presets) == MAX_PRESETS
    assert popup.lbl_count.text() == f"{MAX_PRESETS}/{MAX_PRESETS}"


def test_pin_button_flashes_hint_when_full(popup):
    popup.slider.setValue(140)
    popup._pin_current_speed()
    popup.slider.setValue(175)
    popup.btn_pin.click()
    assert "FFB340" in popup.lbl_count.styleSheet(), "the 6/6 counter lights up"
    assert len(popup.presets) == MAX_PRESETS


def test_pin_button_toggles_off_for_pinned_speed(popup):
    popup.slider.setValue(125)                          # 1.25 is a default preset
    assert popup._is_pinned(1.25)
    popup.btn_pin.click()
    assert 1.25 not in popup.presets


def test_reset_restores_defaults(popup):
    popup._unpin_preset(1.2)
    popup._reset_to_default_presets()
    assert popup.presets == DEFAULT_PRESETS


def test_presets_persist_across_instances(popup, qapp):
    popup.slider.setValue(140)
    popup._pin_current_speed()
    again = SpeedPopup()
    assert again.presets == popup.presets


def test_oversized_saved_list_is_truncated(qapp):
    from core.settings import open_settings
    import json
    open_settings("SpeedSettings").setValue("custom_presets", json.dumps([1.0, 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7]))
    assert len(SpeedPopup().presets) == MAX_PRESETS


# --- layout: a vertical list, the current speed left of the slider ------------

def test_presets_are_a_vertical_list_above_the_slider_row(popup):
    cs = chips(popup)
    assert len(cs) == len(DEFAULT_PRESETS)
    ys = [c.mapTo(popup, c.rect().topLeft()).y() for c in cs]
    assert ys == sorted(ys) and len(set(ys)) == len(ys), "one row under the other"
    assert len({c.x() for c in cs}) == 1
    row_y = popup.slider.mapTo(popup, popup.slider.rect().topLeft()).y()
    assert row_y > max(ys), "the slider is under the list"
    left = popup.lbl_speed_val.mapTo(popup, popup.lbl_speed_val.rect().topLeft()).x()
    assert popup.btn_pin.x() < left < popup.slider.x(), "pin, current speed, slider - from the left"
    assert popup.width() == 190


def test_panel_grows_downwards_only_when_a_preset_is_added(qapp):
    host = QWidget()
    host.resize(700, 500)
    anchor = QWidget(host)
    anchor.setGeometry(300, 440, 60, 30)
    p = SpeedPopup(host)
    host.show()
    p.show_above_widget(anchor)
    bottom, height = p.y() + p.height(), p.height()
    p.slider.setValue(140)
    assert p._pin_current_speed() is True
    assert p.height() > height, "a sixth row makes the panel taller"
    assert p.y() + p.height() == bottom, "...upwards, so it never creeps over the controls"
    p._unpin_preset(1.4)
    assert p.height() == height and p.y() + p.height() == bottom
    host.close()


# --- typing a speed in -------------------------------------------------------

def test_parse_speed_input():
    from ui.speed_popup import parse_speed_input
    assert parse_speed_input("1.5") == 1.5
    assert parse_speed_input(" 1.50x ") == 1.5
    assert parse_speed_input("1,3") == 1.3
    assert parse_speed_input("1.33") == 1.35, "snaps to the 0.05 grid"
    assert parse_speed_input("0.1") == 0.25 and parse_speed_input("9") == 3.0, "stays inside the slider's range"
    for bad in ("", "x", "abc", "nan", "inf", "1..2"):
        assert parse_speed_input(bad) is None


def type_speed(popup, text):
    popup.lbl_speed_val.clicked.emit()
    assert popup.is_editing_speed()
    popup.edit_speed.setText(text)


def test_clicking_the_speed_text_opens_a_box_and_enter_applies(popup):
    emitted = []
    popup.speed_selected.connect(emitted.append)
    popup.lbl_speed_val.clicked.emit()
    assert popup.is_editing_speed() and popup.edit_speed.text() == "1.00"
    type_speed(popup, "1.35")
    QTest.keyClick(popup.edit_speed, Qt.Key_Return)
    assert not popup.is_editing_speed()
    assert emitted[-1] == 1.35 and popup.slider.value() == 135
    assert popup.lbl_speed_val.text() == "1.35x"


def test_escape_or_clicking_away_cancels_typing(popup):
    emitted = []
    popup.speed_selected.connect(emitted.append)
    type_speed(popup, "2.5")
    QTest.keyClick(popup.edit_speed, Qt.Key_Escape)
    assert not popup.is_editing_speed() and not emitted and popup.slider.value() == 100
    assert popup.isVisible(), "Esc in the box closes the box, not the panel"
    type_speed(popup, "2.5")
    popup.edit_speed.clearFocus()                      # focus leaves the box
    assert not popup.is_editing_speed() and not emitted


def test_nonsense_typed_in_leaves_the_speed_alone(popup):
    emitted = []
    popup.speed_selected.connect(emitted.append)
    type_speed(popup, "fast")
    QTest.keyClick(popup.edit_speed, Qt.Key_Return)
    assert not popup.is_editing_speed() and not emitted and popup.lbl_speed_val.text() == "1.00x"


# --- per-chip delete -------------------------------------------------------

def test_chip_x_deletes_only_that_preset(popup):
    target = chips(popup)[2]                            # 1.25x
    target.btn_x.click()
    assert popup.presets == [p for p in DEFAULT_PRESETS if p != target.speed]


def test_chip_x_appears_on_hover_only(popup, qapp):
    cs = chips(popup)
    assert not any(c.btn_x.isVisibleTo(popup) for c in cs)
    first = cs[0]
    first.enterEvent(QEnterEvent(QPointF(5, 5), QPointF(5, 5), QPointF(5, 5)))
    assert first.btn_x.isVisibleTo(popup)
    assert not any(c.btn_x.isVisibleTo(popup) for c in cs[1:])


def test_chip_click_applies_speed(popup):
    emitted = []
    popup.speed_selected.connect(emitted.append)
    chips(popup)[3].click()                             # 1.5x
    assert emitted[-1] == 1.5
    assert popup.slider.value() == 150


def test_active_chip_follows_external_speed(popup):
    popup.set_current_speed(2.0)
    assert popup.lbl_speed_val.text() == "2.00x"
    assert popup.slider.value() == 200


def test_popup_stays_inside_parent(qapp):
    host = QWidget()
    host.resize(500, 300)
    anchor = QWidget(host)
    anchor.setGeometry(10, 250, 60, 30)                 # near the left/bottom edge
    popup = SpeedPopup(host)
    host.show()
    popup.show_above_widget(anchor)
    assert popup.x() >= 0 and popup.y() >= 0
    assert popup.x() + popup.width() <= host.width()
    host.close()


def test_toggle_above_widget(qapp):
    host = QWidget()
    host.resize(600, 300)
    anchor = QWidget(host)
    anchor.setGeometry(100, 250, 60, 30)
    popup = SpeedPopup(host)
    host.show()
    popup.toggle_above_widget(anchor)
    assert popup.isVisible()
    popup.toggle_above_widget(anchor)
    assert not popup.isVisible()
    host.close()


# --- OSD -------------------------------------------------------------------

@pytest.fixture
def osd(qapp):
    host = QWidget()
    host.resize(600, 400)
    o = GlassOSDWidget(host)
    host.show()
    yield o
    host.close()


def test_osd_shows_text_and_icon(osd):
    osd.show_message("1.40x", "speed")
    assert osd.isVisible()
    assert osd.text_label.text() == "1.40x"
    assert osd.icon_label.isVisibleTo(osd) and osd.icon_label.pixmap() is not None


def test_osd_without_or_with_unknown_icon_hides_icon(osd):
    osd.show_message("hello")
    assert not osd.icon_label.isVisibleTo(osd)
    osd.show_message("hello", "not-an-icon")
    assert not osd.icon_label.isVisibleTo(osd)


def test_osd_fades_out_after_hold(osd, pump):
    osd.show_message("bye", "check")
    assert pump(lambda: not osd.isVisible(), timeout=2.5), "OSD did not fade out"


# --- where the panel opens -----------------------------------------------------

def test_panel_opens_at_the_left_margin_when_asked_else_centred_on_the_anchor(qapp):
    host = QWidget()
    host.resize(700, 400)
    anchor = QWidget(host)
    anchor.setGeometry(300, 350, 60, 30)
    margin = QWidget(host)
    margin.setGeometry(24, 350, 150, 30)
    popup = SpeedPopup(host)
    host.show()
    popup.show_above_widget(anchor, align_to=margin)
    assert popup.x() == 24, "left edge on the controls' left margin: the bottom-left corner"
    assert popup.y() + popup.height() < anchor.y()
    popup.hide()
    popup.show_above_widget(anchor)
    assert popup.x() == anchor.x() + (anchor.width() - popup.width()) // 2
    popup.hide()
    margin.hide()
    popup.show_above_widget(anchor, align_to=margin)
    assert popup.x() == anchor.x() + (anchor.width() - popup.width()) // 2, "a hidden margin widget is ignored"
    host.close()
