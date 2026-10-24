"""The bookmark list panel: rows, rename, delete, jump, and how it is dismissed (a real widget, real events)."""
import pytest
from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QEnterEvent, QKeyEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLineEdit, QPushButton, QWidget

from core.media_info import format_clock
from ui.bookmark_panel import BookmarkPanel, _BookmarkRow

ITEMS = [{"t": 125.0, "name": ""}, {"t": 760.0, "name": "증명 다시 보기"}, {"t": 1800.0, "name": ""}]


@pytest.fixture
def host(qapp):
    h = QWidget()
    h.resize(900, 600)
    h.show()
    yield h
    h.close()


@pytest.fixture
def panel(qapp, host):
    p = BookmarkPanel(host)
    p.set_items(ITEMS, 3860.0)
    p.show()
    qapp.processEvents()
    return p


def rows(p):
    return p.findChildren(_BookmarkRow)


def hover(row):
    QApplication.sendEvent(row, QEnterEvent(QPointF(5, 5), QPointF(5, 5), QPointF(5, 5)))


def edit_field(p):
    fields = p.findChildren(QLineEdit)
    return fields[0] if fields else None


def test_rows_show_the_name_or_the_time_and_the_time(panel):
    got = [(r.name_text(), r.time_text()) for r in rows(panel)]
    assert got == [(format_clock(125.0), format_clock(125.0)), ("증명 다시 보기", format_clock(760.0)),
                   (format_clock(1800.0), format_clock(1800.0))]
    assert all(r.height() == 44 for r in rows(panel)) and panel.width() == 380


def test_the_count_and_the_empty_state(qapp, panel):
    assert panel.count_label.text() == "3개" and not panel.empty_label.isVisible()
    panel.set_items([], 3860.0)
    qapp.processEvents()
    assert rows(panel) == [] and panel.count_label.text() == "0개"
    assert panel.empty_label.isVisible()
    assert panel.empty_label.text() == "아직 북마크가 없어요 · B 로 지금 위치를 저장해요"
    assert "Alt + ←" in panel.hint_label.text()


def test_clicking_a_row_asks_to_jump(panel):
    got = []
    panel.jump_requested.connect(got.append)
    QTest.mouseClick(rows(panel)[1], Qt.LeftButton, Qt.NoModifier, rows(panel)[1].rect().center())
    assert got == [760.0]


def test_the_add_button_asks_to_add(panel):
    got = []
    panel.add_requested.connect(lambda: got.append(1))
    assert panel.add_button.text() == "지금 위치  B"
    panel.add_button.click()
    assert got == [1]


def test_the_pencil_opens_an_edit_field_and_enter_saves_the_new_name(qapp, panel):
    got = []
    panel.rename_requested.connect(lambda t, name: got.append((t, name)))
    row = rows(panel)[1]
    hover(row)
    assert not panel.is_editing
    row.edit_button.click()
    field = edit_field(panel)
    assert field is not None and panel.is_editing and field.text() == "증명 다시 보기"
    field.setText("새 이름")
    QTest.keyClick(field, Qt.Key_Return)
    assert got == [(760.0, "새 이름")]
    qapp.processEvents()
    assert not panel.is_editing and edit_field(panel) is None


def test_a_bookmark_without_a_name_starts_the_edit_empty_with_the_time_as_hint(panel):
    row = rows(panel)[0]
    hover(row)
    row.edit_button.click()
    field = edit_field(panel)
    assert field.text() == "" and field.placeholderText() == format_clock(125.0)


def test_escape_cancels_the_edit_and_a_second_escape_closes_the_panel(qapp, panel):
    got = []
    panel.rename_requested.connect(lambda t, name: got.append((t, name)))
    row = rows(panel)[1]
    hover(row)
    row.edit_button.click()
    field = edit_field(panel)
    field.setText("버릴 이름")
    QTest.keyClick(field, Qt.Key_Escape)
    qapp.processEvents()
    assert got == [] and not panel.is_editing and panel.isVisible(), "the first Escape only ends the edit"
    QTest.keyClick(panel, Qt.Key_Escape)
    assert not panel.isVisible()


def test_an_empty_name_is_saved_as_empty(panel):
    got = []
    panel.rename_requested.connect(lambda t, name: got.append((t, name)))
    row = rows(panel)[1]
    hover(row)
    row.edit_button.click()
    field = edit_field(panel)
    field.setText("   ")
    QTest.keyClick(field, Qt.Key_Return)
    assert got == [(760.0, "")], "back to showing the time"


def test_the_x_asks_to_delete_at_once(panel):
    got = []
    panel.delete_requested.connect(got.append)
    row = rows(panel)[2]
    hover(row)
    row.delete_button.click()
    assert got == [1800.0]


def test_a_bookmark_beyond_the_length_is_dimmed_and_does_not_ask_to_jump(qapp, panel):
    panel.set_items(ITEMS, 1000.0)
    qapp.processEvents()
    got = []
    panel.jump_requested.connect(got.append)
    late = rows(panel)[2]
    assert late.dimmed and not rows(panel)[1].dimmed
    QTest.mouseClick(late, Qt.LeftButton, Qt.NoModifier, late.rect().center())
    assert got == []
    deleted = []
    panel.delete_requested.connect(deleted.append)
    hover(late)
    late.delete_button.click()
    assert deleted == [1800.0], "a dimmed one can still be removed"


def test_a_click_outside_closes_it(qapp, host, panel):
    other = QWidget(host)
    other.setGeometry(700, 450, 50, 50)           # (far from the panel, which sits at the corner without an anchor)
    other.show()
    qapp.processEvents()
    QTest.mouseClick(other, Qt.LeftButton)
    assert not panel.isVisible()


def test_a_click_inside_does_not_close_it(qapp, panel):
    QTest.mouseClick(panel, Qt.LeftButton, Qt.NoModifier, panel.rect().center())
    assert panel.isVisible()


def test_typing_in_the_edit_field_does_not_leave_the_panel(qapp, panel):
    row = rows(panel)[0]
    hover(row)
    row.edit_button.click()
    field = edit_field(panel)
    QTest.keyClicks(field, "bB ")
    assert field.text() == "bB " and panel.isVisible() and panel.is_editing


def test_it_floats_above_the_anchor_inside_the_window(qapp, host):
    anchor = QPushButton("b", host)
    anchor.setGeometry(800, 540, 40, 40)
    anchor.show()
    p = BookmarkPanel(host)
    p.set_items(ITEMS, 3860.0)
    p.toggle_above_widget(anchor)
    qapp.processEvents()
    assert p.isVisible() and p.geometry().bottom() < anchor.geometry().top()
    assert host.rect().contains(p.geometry())
    p.toggle_above_widget(anchor)
    assert not p.isVisible()


@pytest.mark.parametrize("key", [Qt.Key_Return, Qt.Key_Enter, Qt.Key_Escape])
def test_enter_and_escape_in_the_edit_field_are_consumed_so_the_player_never_sees_them(qapp, panel, key):
    """A QLineEdit leaves Return unaccepted so it travels up to the parent: there it would toggle full screen."""
    row = rows(panel)[0]
    hover(row)
    row.edit_button.click()
    field = edit_field(panel)
    event = QKeyEvent(QEvent.KeyPress, key, Qt.NoModifier)
    QApplication.sendEvent(field, event)
    assert event.isAccepted()
