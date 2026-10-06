"""Animated glass buttons: size, brightness-only press feedback, icon cross-fade, controller wiring."""
import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QWidget

from ui import glass_button
from ui.glass_button import GlassButton
from ui.glass_controller import GlassController, PLAY_DISC, SIDE_DISC
from ui.icons import get_svg_icon


@pytest.fixture
def host(qapp):
    h = QWidget()
    h.resize(1000, 700)
    h.show()
    return h


@pytest.fixture
def controller(host, qapp):
    c = GlassController(host)
    c.setGeometry(0, 700 - c.STRIP_HEIGHT, 1000, c.STRIP_HEIGHT)
    c.set_media_loaded(True)
    c.show()
    qapp.processEvents()
    return c


def _luma(c: QColor) -> float:
    return (0.299 * c.red() + 0.587 * c.green() + 0.114 * c.blue()) * c.alphaF()


def _body_sample(btn):
    """Mean brightness of a few body pixels away from the icon and the rim, over a fixed dark backdrop."""
    from PySide6.QtGui import QImage, QPainter
    img = QImage(btn.size(), QImage.Format_ARGB32)
    img.fill(QColor(20, 24, 32))
    p = QPainter(img)
    btn.render(p, QPoint(0, 0))
    p.end()
    m, r = btn._m, btn._d / 2
    cx = cy = btn.width() / 2
    pts = [(cx - r * 0.78, cy), (cx + r * 0.78, cy), (cx, cy - r * 0.78), (cx, cy + r * 0.78)]
    return sum(_luma(img.pixelColor(int(x), int(y))) for x, y in pts) / len(pts)


def test_transport_buttons_are_glass_discs_with_the_designed_sizes(controller):
    m = glass_button.DISC_MARGIN
    assert isinstance(controller.btn_play, GlassButton) and controller.btn_play.kind == "disc"
    assert controller.btn_play.size().toTuple() == (PLAY_DISC + 2 * m,) * 2
    sides = [b for b in controller.findChildren(GlassButton) if b.kind == "disc" and b is not controller.btn_play]
    assert len(sides) == 2
    for b in sides:
        assert b.size().toTuple() == (SIDE_DISC + 2 * m,) * 2


def test_controller_qss_does_not_resize_the_glass_buttons(controller):
    """Regression: QSS min/max sizes beat setFixedSize, which squeezed every button to its icon."""
    for b in controller.findChildren(GlassButton):
        want_w, want_h = b._content_width() + 2 * b._m, b._d + 2 * b._m
        assert (b.width(), b.height()) == (want_w, want_h), (b.toolTip(), b.size())


def test_every_icon_button_animates(controller):
    kinds = {b.toolTip().split(" ")[0]: b.kind for b in controller.findChildren(GlassButton)}
    assert len(kinds) >= 8
    assert all(b.cursor().shape() == Qt.PointingHandCursor for b in controller.findChildren(GlassButton))


def test_play_controls_fit_inside_the_hover_zone(controller):
    top = controller.btn_play.mapTo(controller, QPoint(0, 0)).y()
    assert top >= controller.height() - controller.CONTROLS_HEIGHT


def test_press_and_hover_only_change_brightness_never_the_size(controller, qapp):
    b = controller.btn_play
    rest_size, rest_geo = b.size(), b.geometry()
    rest = _body_sample(b)
    b._hover = 1.0
    hover = _body_sample(b)
    b._press = 1.0
    press = _body_sample(b)
    assert hover > rest + 1.0, (rest, hover)
    assert press > hover + 1.0, (hover, press)
    assert b.size() == rest_size and b.geometry() == rest_geo
    assert not hasattr(b, "_scale"), "pressed glass must not shrink"


def test_press_animation_runs_and_settles(controller, pump):
    b = controller.btn_play
    b._animate("press", 1.0, 60)
    assert pump(lambda: abs(b._press - 1.0) < 0.01, timeout=1.0)
    b._animate("press", 0.0, 120)
    assert pump(lambda: b._press < 0.01, timeout=1.5)


def test_real_press_and_release_drive_the_press_state(controller, qapp, pump):
    from PySide6.QtTest import QTest
    b = controller.btn_play
    QTest.mousePress(b, Qt.LeftButton, Qt.NoModifier, b.rect().center())
    assert pump(lambda: b._press > 0.9, timeout=1.0)
    QTest.mouseRelease(b, Qt.LeftButton, Qt.NoModifier, b.rect().center())
    assert pump(lambda: b._press < 0.05, timeout=1.5)


def test_icon_cross_fades_when_the_state_changes(controller, pump):
    controller.set_playback_state(False)
    pump(timeout=0.3)
    b = controller.btn_play
    controller.set_playback_state(True)                      # play -> pause
    assert b._prev_icon is not None and b._fade < 1.0
    assert pump(lambda: b._fade >= 1.0, timeout=1.5)


def test_icon_swap_while_hidden_does_not_animate(host):
    b = GlassButton(host, "plain", 40, 16)
    b.setIcon(get_svg_icon("play_glass", size=16))
    b.setIcon(get_svg_icon("pause_glass", size=16))
    assert b._fade == 1.0 and b._prev_icon is None


def test_plain_button_highlight_fades_in(host, qapp, pump):
    from PySide6.QtGui import QImage, QPainter
    b = GlassButton(host, "plain", 40, 16)
    b.move(10, 10)
    b.show()
    qapp.processEvents()

    def lum():
        img = QImage(b.size(), QImage.Format_ARGB32)
        img.fill(QColor(20, 24, 32))
        p = QPainter(img)
        b.render(p, QPoint(0, 0))
        p.end()
        return _luma(img.pixelColor(6, 20))
    rest = lum()
    b._animate("hover", 1.0, 80)
    assert pump(lambda: b._hover > 0.99, timeout=1.0)
    assert lum() > rest + 3


def test_glass_icons_are_rounded_not_sharp():
    """The transport icons use curves (Q commands), not straight polygons."""
    from ui.icons import SVG_ICONS
    for name in ("play_glass", "backward_glass", "forward_glass", "prev_frame_glass", "next_frame_glass"):
        assert " Q" in SVG_ICONS[name], name
    assert 'rx="2"' in SVG_ICONS["pause_glass"]


def test_backward_and_forward_icons_are_mirror_images(qapp):
    from ui.icons import get_svg_pixmap
    back = get_svg_pixmap("backward_glass", 24).toImage()
    fwd = get_svg_pixmap("forward_glass", 24).toImage().mirrored(True, False)
    diff = sum(abs(back.pixelColor(x, y).alpha() - fwd.pixelColor(x, y).alpha())
               for x in range(back.width()) for y in range(back.height()))
    assert diff < 600, diff


def test_icon_swap_shrinks_the_old_icon_and_grows_the_new_one_without_a_muddy_overlap():
    from ui.glass_button import icon_swap_params
    o0, os0, n0, ns0 = icon_swap_params(0.0)
    assert (o0, os0, n0) == (1.0, 1.0, 0.0) and ns0 < 0.85
    o1, os1, n1, ns1 = icon_swap_params(1.0)
    assert (o1, n1, ns1) == (0.0, 1.0, 1.0) and os1 < 0.85
    prev_old, prev_new = 1.0, 0.0
    for i in range(1, 101):
        o, _s1, n, _s2 = icon_swap_params(i / 100)
        assert o <= prev_old + 1e-9 and n >= prev_new - 1e-9, "old only fades out, new only fades in"
        prev_old, prev_new = o, n
    # never both mostly visible at the same time (that is what looked like a flicker)
    assert max(min(icon_swap_params(i / 100)[0], icon_swap_params(i / 100)[2]) for i in range(101)) < 0.45


def test_state_transitions_are_not_abrupt():
    assert glass_button.HOVER_MS >= 150 and glass_button.PRESS_OUT_MS >= 250 and glass_button.ICON_FADE_MS >= 250
