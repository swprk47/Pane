"""The control-bar settings: edit the bar the way it looks (drag buttons between zones, hide, bring back)."""
import pytest
from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QWidget

from ui.glass_controller import BUTTON_METADATA, DEFAULT_LAYOUT
from ui.layout_dialog import LayoutEditor, ZONES, DIALOG_CONTENT_W
from ui.settings_panel import SettingsPanel


@pytest.fixture
def editor(qapp):
    host = QWidget()
    host.resize(700, 400)
    ed = LayoutEditor(DEFAULT_LAYOUT, BUTTON_METADATA, DEFAULT_LAYOUT, host)
    ed.setFixedWidth(DIALOG_CONTENT_W - 48)
    ed.fit()
    host.show()
    qapp.processEvents()
    yield ed
    host.close()


def pt(p: QPointF) -> QPoint:
    return p.toPoint()


def hover(ed, pos: QPointF):
    """A plain mouse move (QTest.mouseMove sends none to a widget unless a button is down)."""
    QApplication.sendEvent(ed, QMouseEvent(QEvent.MouseMove, pos, ed.mapToGlobal(pos), Qt.NoButton, Qt.NoButton, Qt.NoModifier))


def drag(ed, start: QPointF, end: QPointF):
    QTest.mousePress(ed, Qt.LeftButton, Qt.NoModifier, pt(start))
    QTest.mouseMove(ed, pt(start + QPointF(14, 2)))             # past the drag threshold
    QTest.mouseMove(ed, pt(end))
    QTest.mouseRelease(ed, Qt.LeftButton, Qt.NoModifier, pt(end))


# --- what is on the bar and what is hidden -------------------------------------------------------

def test_the_default_layout_hides_the_frame_buttons_and_lists_them(editor):
    assert editor.layout() == {z: DEFAULT_LAYOUT[z] for z in ZONES}
    assert set(editor.hidden_keys()) == {"prev_frame", "next_frame"}


def test_every_button_is_placed_or_hidden_exactly_once(editor):
    placed = [k for z in ZONES for k in editor.layout()[z]]
    everything = placed + editor.hidden_keys()
    assert sorted(everything) == sorted(BUTTON_METADATA) and len(set(everything)) == len(everything)


def test_set_layout_ignores_unknown_and_repeated_buttons(editor):
    editor.set_layout({"left": ["volume", "nope", "volume"], "center": ["volume", "play_pause"], "right": []})
    assert editor.layout() == {"left": ["volume"], "center": ["play_pause"], "right": []}
    assert "volume" not in editor.hidden_keys() and "settings" in editor.hidden_keys()


def test_move_key_between_zones_hide_and_bring_back(editor):
    seen = []
    editor.changed.connect(lambda: seen.append(1))
    editor.move_key("seek_forward", "left", 0)
    assert editor.layout()["left"][0] == "seek_forward" and "seek_forward" not in editor.layout()["center"]
    editor.move_key("seek_forward", "hidden")
    assert editor.zone_of("seek_forward") is None and "seek_forward" in editor.hidden_keys()
    editor.move_key("prev_frame", "center", 1)
    assert editor.layout()["center"][1] == "prev_frame" and "prev_frame" not in editor.hidden_keys()
    editor.move_key("not_a_button", "left")
    assert len(seen) == 3, "only real changes are announced"


# --- the picture of the bar ------------------------------------------------------------------------

def test_default_buttons_sit_on_one_row_inside_their_zones(editor):
    for z in ZONES:
        zr = editor.zone_rect(z)
        rects = [editor.item_rect(k) for k in editor.layout()[z]]
        assert rects and all(zr.contains(r) for r in rects), z
        assert len({round(r.top()) for r in rects}) == 1, f"{z}: one row"
        xs = sorted(r.left() for r in rects)
        assert all(b - a >= 47 for a, b in zip(xs, xs[1:])), f"{z}: no overlap"
    assert editor.zone_rect("left").right() < editor.zone_rect("center").left() < editor.zone_rect("center").right() \
        < editor.zone_rect("right").left()


def test_a_crowded_zone_wraps_to_a_second_row_and_the_editor_grows(editor):
    h = editor.height()
    editor.set_layout({"left": ["time_label", "speed_button", "prev_file", "next_file"], "center": ["play_pause"], "right": []})
    rows = {round(editor.item_rect(k).top()) for k in editor.layout()["left"]}
    assert len(rows) == 2, "left holds two across, so four buttons need two rows"
    assert editor.height() > h or editor.height() >= 150
    editor.set_layout(DEFAULT_LAYOUT)
    assert editor.height() == h


def test_hidden_buttons_are_chips_below_the_bar(editor):
    for k in ("prev_frame", "next_frame"):
        assert editor.item_rect(k).top() >= editor.tray_rect().top()
    assert editor.tray_rect().top() > editor.zone_rect("left").bottom()


# --- dragging --------------------------------------------------------------------------------------

def test_dragging_a_button_into_another_zone_puts_it_where_it_is_dropped(editor):
    r = editor.item_rect("next_file").center()
    left = editor.zone_rect("left")
    drag(editor, r, QPointF(left.left() + 6, left.center().y()))        # the very front of the left zone
    assert editor.layout()["left"][0] == "next_file"
    assert "next_file" not in editor.layout()["center"]


def test_dragging_inside_a_zone_reorders_it(editor):
    first, last = editor.item_rect("prev_file").center(), editor.item_rect("next_file").center()
    drag(editor, first, QPointF(last.x() + 30, last.y()))
    assert editor.layout()["center"] == ["seek_backward", "play_pause", "seek_forward", "next_file", "prev_file"]


def test_dragging_a_button_down_to_the_tray_hides_it(editor):
    drag(editor, editor.item_rect("screenshot").center(), editor.tray_rect().center())
    assert editor.zone_of("screenshot") is None and "screenshot" in editor.hidden_keys()


def test_dragging_a_hidden_chip_up_into_a_zone_brings_it_back_there(editor):
    chip = editor.item_rect("prev_frame").center()
    right = editor.zone_rect("right")
    drag(editor, chip, QPointF(right.right() - 4, right.center().y()))
    assert editor.layout()["right"][-1] == "prev_frame" and "prev_frame" not in editor.hidden_keys()


def test_a_drop_outside_everything_changes_nothing(editor):
    before = editor.layout()
    drag(editor, editor.item_rect("volume").center(), QPointF(editor.width() + 200, editor.height() + 200))
    assert editor.layout() == before and "volume" not in editor.hidden_keys()


def test_a_tiny_movement_is_a_click_not_a_drag(editor):
    before = editor.layout()
    c = pt(editor.item_rect("volume").center())
    QTest.mousePress(editor, Qt.LeftButton, Qt.NoModifier, c)
    QTest.mouseMove(editor, c + QPoint(1, 1))
    QTest.mouseRelease(editor, Qt.LeftButton, Qt.NoModifier, c + QPoint(1, 1))
    assert editor.layout() == before


def test_clicking_a_hidden_chip_brings_it_back_to_its_usual_zone(editor):
    editor.move_key("volume", "hidden")
    c = pt(editor.item_rect("volume").center())
    QTest.mouseClick(editor, Qt.LeftButton, Qt.NoModifier, c)
    assert editor.layout()["right"][-1] == "volume"
    assert editor.default_zone("prev_frame") == "right", "a button the default layout does not place goes to the right"


def test_the_x_on_a_hovered_button_hides_it(editor):
    r = editor.item_rect("fullscreen")
    hover(editor, r.center())                                            # hover first: the x only shows then
    badge = editor._x_badge("fullscreen")
    QTest.mouseClick(editor, Qt.LeftButton, Qt.NoModifier, pt(badge.center()))
    assert editor.zone_of("fullscreen") is None and "fullscreen" in editor.hidden_keys()


# --- the panel (laid over the player window, not a window of its own) --------------------------

@pytest.fixture
def panel(qapp):
    host = QWidget()
    host.resize(900, 600)
    host.show()
    p = SettingsPanel(DEFAULT_LAYOUT, BUTTON_METADATA, DEFAULT_LAYOUT, host)
    p.open()
    qapp.processEvents()
    yield p
    p.reject()
    host.close()


def test_apply_sends_the_new_layout_and_cancel_does_not(panel):
    got = []
    panel.layout_changed.connect(got.append)
    panel.editor.move_key("prev_frame", "center", 0)
    panel.btn_cancel.click()
    assert got == []

    # (cancel closed that one: open a new one for the second half)
    host = panel._host
    again = SettingsPanel(DEFAULT_LAYOUT, BUTTON_METADATA, DEFAULT_LAYOUT, host)
    again.layout_changed.connect(got.append)
    again.open()
    again.editor.move_key("prev_frame", "center", 0)
    again.btn_apply.click()
    assert got and got[0]["center"][0] == "prev_frame"
    assert set(got[0]) == set(ZONES)


def test_reset_puts_the_default_layout_back_including_the_hidden_frame_buttons(panel):
    panel.editor.move_key("prev_frame", "left", 0)
    panel.editor.move_key("volume", "hidden")
    panel.btn_reset.click()
    assert panel.editor.layout() == {z: DEFAULT_LAYOUT[z] for z in ZONES}
    assert "prev_frame" in panel.editor.hidden_keys()


def test_it_is_a_widget_inside_the_window_not_a_window(panel):
    """A second translucent top-level window made the player flicker when it opened."""
    assert not panel.isWindow()
    assert panel.parentWidget() is panel._host


def test_the_window_behind_is_dimmed_while_the_panel_is_open(panel):
    assert panel._dim is not None and panel._dim.isVisible()
    assert panel._dim.geometry() == panel._host.rect()
    finished = []
    panel.finished.connect(finished.append)
    panel.reject()
    assert panel._dim is None and not panel.isVisible()
    assert finished == [False]


def test_it_sits_in_the_middle_of_the_window_and_follows_its_size(panel, qapp):
    host = panel._host
    assert abs(panel.geometry().center().x() - host.rect().center().x()) <= 1
    assert abs(panel.geometry().center().y() - host.rect().center().y()) <= 1
    host.resize(1300, 800)
    qapp.processEvents()
    assert abs(panel.geometry().center().x() - host.rect().center().x()) <= 1
    assert panel._dim.geometry() == host.rect()


def test_dragging_the_header_moves_it_inside_the_window(panel, qapp):
    start = panel.pos()
    press = QPoint(60, 40)                                              # in the header
    QTest.mousePress(panel, Qt.LeftButton, Qt.NoModifier, press)
    QApplication.sendEvent(panel, QMouseEvent(QEvent.MouseMove, QPointF(press + QPoint(-30, 20)), Qt.NoButton, Qt.LeftButton, Qt.NoModifier))
    QTest.mouseRelease(panel, Qt.LeftButton, Qt.NoModifier, press + QPoint(-30, 20))
    assert panel.pos() == start + QPoint(-30, 20)
    panel._host.resize(1000, 650)
    qapp.processEvents()
    assert panel.x() == start.x() - 30, "once moved by hand it stays where the user put it"


# --- modal: nothing behind it reacts ---------------------------------------------------------

def test_settings_button_opens_the_panel_and_apply_changes_the_bar(window, pump):
    c = window.controller
    c._open_settings_dialog()
    p = c.settings_panel
    assert isinstance(p, SettingsPanel) and p.isVisible()
    c._open_settings_dialog()
    assert c.settings_panel is p, "pressing the button again does not open a second one"
    p.editor.move_key("prev_frame", "center", 0)
    p.btn_apply.click()
    assert c.settings_panel is None
    assert c.current_layout["center"][0] == "prev_frame"
    assert hasattr(c, "btn_prev_file") and c.center_box.count() == len(c.current_layout["center"])


def test_the_players_shortcuts_are_off_while_it_is_open_and_esc_closes_it(window, pump):
    c = window.controller
    c._open_settings_dialog()
    assert c.settings_panel is not None
    QTest.keyClick(window, Qt.Key_F)                                     # fullscreen: swallowed
    QTest.keyClick(c.settings_panel, Qt.Key_M)                             # (also when the panel itself has the focus)
    assert not window.isFullScreen()
    QTest.keyClick(window, Qt.Key_Escape)
    assert c.settings_panel is None


def test_the_controls_stay_up_while_the_panel_is_open(window):
    c = window.controller
    c._open_settings_dialog()
    c.autohide_timer.stop()
    c._fade_out()
    assert c.autohide_timer.isActive(), "the bar being edited must not fade away behind the panel"
    c.settings_panel.reject()


def test_it_stays_on_top_when_the_window_lays_its_widgets_out_again(window):
    c = window.controller
    c._open_settings_dialog()
    window._reposition_floating_widgets()
    kids = window.central_widget.children()
    assert kids.index(c.settings_panel) > kids.index(c) and kids.index(c.settings_panel._dim) > kids.index(c)
    assert kids.index(c.settings_panel) > kids.index(c.settings_panel._dim)
    c.settings_panel.reject()


def test_a_click_on_the_dimmed_window_is_swallowed(window):
    c = window.controller
    c._open_settings_dialog()
    window.viewport.start_screen.hide()
    toggles = []
    window.engine.toggle_play = lambda: toggles.append(1)
    dim = c.settings_panel._dim
    QTest.mouseClick(dim, Qt.LeftButton, Qt.NoModifier, QPoint(5, 5))
    assert toggles == [] and c.settings_panel is not None
    c.settings_panel.reject()
