"""ThumbnailTip: the picture above the time pill (drawn for real, never grab(): it paints an opaque background)."""
import pytest
from PySide6.QtCore import QPoint, QRect
from PySide6.QtGui import QColor, QImage, QRegion
from PySide6.QtWidgets import QWidget

from ui.overlay import ThumbnailTip


@pytest.fixture
def host(qapp):
    h = QWidget()
    h.resize(800, 600)
    h.show()
    qapp.processEvents()
    yield h
    h.close()


def solid(w, h, color=(220, 30, 30)):
    img = QImage(w, h, QImage.Format_RGB32)
    img.fill(QColor(*color))
    return img


def render(tip) -> QImage:
    img = QImage(tip.size(), QImage.Format_ARGB32_Premultiplied)
    img.fill(0)
    tip.render(img, QPoint(), QRegion(), QWidget.RenderFlag(0))
    return img


def is_red(c):
    return c.red() > 180 and c.green() < 80 and c.alpha() > 240


def test_it_is_hidden_until_used_and_hide_tip_hides_it(host):
    tip = ThumbnailTip(host)
    assert not tip.isVisible()
    tip.show_at(solid(320, 180), 400, 300, host.rect())
    assert tip.isVisible()
    tip.hide_tip()
    assert not tip.isVisible()


def test_the_picture_is_drawn_inside_a_rounded_border(host):
    tip = ThumbnailTip(host)
    tip.show_at(solid(320, 180), 400, 300, host.rect())
    assert (tip.width(), tip.height()) == (160, 90)
    img = render(tip)
    assert is_red(img.pixelColor(80, 45)), "the picture fills the middle"
    assert img.pixelColor(0, 0).alpha() < 40, "the corner is cut by the 10 px rounding"
    rim, inside = img.pixelColor(80, 0), img.pixelColor(80, 45)
    assert rim.alpha() > 200 and rim.green() > inside.green() + 60, "a light border along the top edge (white over the red)"


def test_a_wide_and_a_tall_picture_get_the_clamped_box_with_dark_bars(host):
    tip = ThumbnailTip(host)
    tip.show_at(solid(320, 137), 400, 300, host.rect())                  # 21:9
    assert (tip.width(), tip.height()) == (160, 90)
    img = render(tip)
    assert is_red(img.pixelColor(80, 45)) and not is_red(img.pixelColor(80, 6)), "bars above and below, picture in the middle"
    tip.show_at(solid(101, 180), 400, 300, host.rect())                  # 9:16
    assert (tip.width(), tip.height()) == (90, 90)
    img = render(tip)
    assert is_red(img.pixelColor(45, 45)) and not is_red(img.pixelColor(6, 45)), "bars left and right"


def test_it_sits_centred_on_the_pointer_and_stays_inside_the_bounds(host):
    tip = ThumbnailTip(host)
    bounds = QRect(0, 0, 800, 600)
    tip.show_at(solid(320, 180), 400, 300, bounds)
    assert tip.x() == 320 and tip.y() + tip.height() == 300, "centred on x, its bottom edge at y_bottom"
    tip.show_at(solid(320, 180), 10, 300, bounds)
    assert tip.x() == bounds.left() + ThumbnailTip.EDGE
    tip.show_at(solid(320, 180), 795, 300, bounds)
    assert tip.geometry().right() <= bounds.right() - ThumbnailTip.EDGE
