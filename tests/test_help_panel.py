"""The help panel: both layouts, sizing, scrolling and its cues, the almost opaque body, the modal dim."""
import pytest
from PySide6.QtCore import QPoint, QPointF, QRect, Qt
from PySide6.QtGui import QColor, QImage, QWheelEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLabel, QWidget

from ui.help_content import KEY_GROUPS, MOUSE, TIPS
from ui.help_panel import HelpPanel


class Host(QWidget):
    def __init__(self, w, h):
        super().__init__()
        self.resize(w, h)
        self.setStyleSheet("background: rgb(255, 0, 0);")


@pytest.fixture
def make(qapp):
    made = []

    def build(w, h, kind, area=None):
        host = Host(w, h)
        host.show()
        panel = HelpPanel(host)
        panel.show_as(kind, area or QRect(0, 0, w, h))
        qapp.processEvents()
        made.append(host)
        return host, panel
    yield build
    for host in made:
        host.close()
    qapp.processEvents()


def texts(panel, name):
    return [lbl for lbl in panel.findChildren(QLabel) if lbl.objectName() == name]


def test_the_centred_panel_is_centred_and_sized_to_the_area(make):
    _host, p = make(1060, 640, HelpPanel.CENTERED)
    assert (p.width(), p.height()) == (900, 548)
    assert p.geometry().center().x() in (529, 530) and p.geometry().center().y() in (319, 320)
    _host, p = make(1920, 1080, HelpPanel.CENTERED)
    assert (p.width(), p.height()) == (900, 640)


@pytest.mark.parametrize("w,h", [(1060, 640), (640, 380), (480, 270)])
def test_the_drawer_is_420_wide_at_the_right_and_inside_the_area(make, w, h):
    host, p = make(w, h, HelpPanel.DRAWER)
    assert p.width() == 420
    assert p.geometry().right() == w - 15, "14 px from the right edge"
    assert p.y() == 46 and p.geometry().bottom() <= h - 14
    assert host.rect().contains(p.geometry())


@pytest.mark.parametrize("kind", [HelpPanel.CENTERED, HelpPanel.DRAWER])
def test_the_body_follows_the_data(make, kind):
    _host, p = make(1060, 640, kind)
    assert len(texts(p, "KeyChip")) == sum(len(chips) for _t, rows in KEY_GROUPS for chips, _d in rows)
    assert len(texts(p, "MouseGesture")) == len(MOUSE) == 6
    assert len(texts(p, "TipText")) == len(TIPS) == 3
    assert p.kind == kind


def test_the_drawer_scrolls_and_the_fade_cues_follow_the_scroll_position(make, qapp):
    _host, p = make(640, 380, HelpPanel.DRAWER)
    bar = p.scroll_area.verticalScrollBar()
    assert bar.maximum() > 0
    assert not p.fade_top() and p.fade_bottom()
    bar.setValue(bar.maximum())
    qapp.processEvents()
    assert p.fade_top() and not p.fade_bottom()
    bar.setValue(bar.maximum() // 2)
    qapp.processEvents()
    assert p.fade_top() and p.fade_bottom()
    assert p._fade_top_w.isVisible() and p._fade_bottom_w.isVisible()
    bar.setValue(0)
    qapp.processEvents()
    assert not p._fade_top_w.isVisible() and p._fade_bottom_w.isVisible()


def test_the_default_window_centred_panel_reaches_every_line(make, qapp):
    _host, p = make(1060, 640, HelpPanel.CENTERED)
    bar = p.scroll_area.verticalScrollBar()
    bar.setValue(bar.maximum())
    qapp.processEvents()
    assert bar.value() == bar.maximum()
    last = texts(p, "TipText")[-1]
    viewport = p.scroll_area.viewport()
    bottom = last.mapTo(viewport, QPoint(0, last.height())).y()
    assert 0 < bottom <= viewport.height()
    assert not p.fade_bottom()


def test_the_body_is_almost_opaque(make):
    host, p = make(1060, 640, HelpPanel.CENTERED)
    img = QImage(host.size(), QImage.Format_ARGB32)
    host.render(img)
    spot = QPoint(p.geometry().center().x(), p.geometry().top() + 28)      # the header row, between its two texts
    assert QColor(img.pixel(spot)).red() < 50, "the red host must not show through the body"   # (measured 37: body + the glass layer)


def test_the_dim_covers_the_area_swallows_the_mouse_and_a_press_asks_to_close(make, qapp):
    host, p = make(1060, 640, HelpPanel.CENTERED)
    asked, reached = [], []
    p.close_requested.connect(lambda: asked.append(1))
    for name in ("mousePressEvent", "mouseReleaseEvent", "mouseDoubleClickEvent", "wheelEvent"):
        setattr(host, name, lambda e, n=name: reached.append(n))
    assert p._dim.geometry().contains(QRect(0, 0, 1060, 640))
    spot = QPoint(20, 20)                                  # on the dim, away from the panel
    target = host.childAt(spot)
    assert target is p._dim, "the dim is the top widget there"
    QTest.mouseClick(target, Qt.LeftButton, Qt.NoModifier, spot)
    assert asked == [1]
    QTest.mouseDClick(target, Qt.LeftButton, Qt.NoModifier, spot)
    QTest.mouseRelease(target, Qt.LeftButton, Qt.NoModifier, spot)
    QApplication.sendEvent(target, QWheelEvent(QPointF(spot), QPointF(spot), QPoint(), QPoint(0, 120), Qt.NoButton, Qt.NoModifier,
                                               Qt.NoScrollPhase, False))
    assert reached == [], "nothing bubbles up to the window behind"
    assert host.children().index(p._dim) < host.children().index(p), "the panel is above its dim"


def test_a_click_inside_the_panel_does_not_reach_what_is_below(make, qapp):
    host, p = make(1060, 640, HelpPanel.DRAWER)
    got = []
    host.mousePressEvent = lambda e: got.append(e)
    QTest.mouseClick(p, Qt.LeftButton, Qt.NoModifier, QPoint(10, 10))
    assert got == []


def test_hide_help_hides_the_panel_and_the_dim(make):
    _host, p = make(1060, 640, HelpPanel.CENTERED)
    assert p.is_open() and p.isVisible() and p._dim.isVisible()
    p.hide_help()
    assert not p.is_open() and not p.isVisible() and not p._dim.isVisible()
    p.show_as(HelpPanel.DRAWER, QRect(0, 0, 1060, 640))
    assert p.is_open() and not p._dim.isVisible(), "the drawer has no dim"


@pytest.mark.parametrize("kind", [HelpPanel.CENTERED, HelpPanel.DRAWER])
def test_no_key_chip_is_clipped_by_its_column(make, kind):
    """(Seen in a real window: the drawer's 150 px column cut `PageDown` off.)"""
    _host, p = make(1060, 640, kind)
    for chip in texts(p, "KeyChip"):
        box = chip.parentWidget()
        needed = box.layout().minimumSize().width()
        assert needed <= box.width(), f"{chip.text()!r}: its row needs {needed}px, the column is {box.width()}px"


@pytest.mark.parametrize("kind", [HelpPanel.CENTERED, HelpPanel.DRAWER])
def test_the_key_chips_are_small_and_all_the_same_height(make, kind):
    """(Polish: the chips were 26 px tall and, with the large text, made the sheet look crude.)"""
    _host, p = make(1060, 640, kind)
    heights = {chip.height() for chip in texts(p, "KeyChip")}
    assert len(heights) == 1 and heights.pop() <= 22


def test_the_centred_panel_needs_no_scrolling_in_the_default_window_and_groups_sit_close(make):
    """(Polish: spare height was shared between the groups as big gaps, and the tips fell below the fold.)"""
    _host, p = make(1060, 640, HelpPanel.CENTERED)
    assert p.scroll_area.verticalScrollBar().maximum() == 0
    titles = sorted(lbl.mapTo(p, QPoint(0, 0)).y() for lbl in p.findChildren(QLabel) if lbl.text() in ("재생", "소리 · 자막"))
    chips = [c.mapTo(p, QPoint(0, 0)).y() for c in texts(p, "KeyChip")]
    last_play_chip = max(y for y in chips if titles[0] < y < titles[1])
    assert titles[1] - last_play_chip < 50, "the next group starts right after the last row of the one above"


def test_the_chips_draw_their_own_smooth_border_a_little_thicker_than_one_pixel(make):
    """(A QSS border of 1 px looked torn on the rounded ends: the chip paints an antialiased 1.5 px outline instead.)"""
    from ui.help_panel import CHIP_BORDER_WIDTH
    _host, p = make(1060, 640, HelpPanel.CENTERED)
    assert CHIP_BORDER_WIDTH == 1.5
    for chip in texts(p, "KeyChip"):
        assert "border" not in chip.styleSheet()
        img = chip.grab().toImage()
        assert img.pixelColor(img.width() // 2, 0).alpha() > 60, "the outline reaches the top edge"


def _group_gap(p):
    titles = sorted(lbl.mapTo(p, QPoint(0, 0)).y() for lbl in p.findChildren(QLabel) if lbl.text() in ("재생", "소리 · 자막"))
    bottoms = [c.mapTo(p, QPoint(0, 0)).y() + c.height() for c in texts(p, "KeyChip")]
    return titles[1] - max(y for y in bottoms if y < titles[1])


def test_in_the_drawer_the_groups_have_more_room_between_them_than_in_the_centred_panel(make):
    _host, centred = make(1060, 640, HelpPanel.CENTERED)
    _host, drawer = make(1060, 640, HelpPanel.DRAWER)
    assert _group_gap(drawer) >= _group_gap(centred) + 8
