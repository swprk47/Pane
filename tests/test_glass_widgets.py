"""Glass sliders, pills, panels and the title bar / popups built from them."""
import pytest
from PySide6.QtCore import QPoint, QPointF, Qt, QRectF
from PySide6.QtGui import QColor, QImage, QPainter, QRegion
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QWidget

from ui import glass_button, glass_slider
from ui.glass_button import GlassButton, paint_glass_panel
from ui.glass_slider import GlassSlider


@pytest.fixture
def host(qapp):
    h = QWidget()
    h.resize(600, 400)
    h.show()
    return h


def _render(widget, bg=(20, 24, 32)):
    img = QImage(widget.size(), QImage.Format_ARGB32)
    img.fill(QColor(*bg))
    p = QPainter(img)
    widget.render(p, QPoint(0, 0))
    p.end()
    return img


def _luma(c):
    return (0.299 * c.red() + 0.587 * c.green() + 0.114 * c.blue()) * c.alphaF()


# --- slider ----------------------------------------------------------------

def test_slider_click_sets_the_value_under_the_pointer(host, qapp):
    s = GlassSlider(Qt.Horizontal, host)
    s.setRange(0, 1000)
    s.setFixedSize(300, 26)
    s.move(10, 10)
    s.show()
    qapp.processEvents()
    QTest.mouseClick(s, Qt.LeftButton, Qt.NoModifier, QPoint(150, 13))
    assert abs(s.value() - 500) <= 30, "a click jumps to the pointer (no page-step crawl)"
    QTest.mouseClick(s, Qt.LeftButton, Qt.NoModifier, QPoint(2, 13))
    assert s.value() == 0
    QTest.mouseClick(s, Qt.LeftButton, Qt.NoModifier, QPoint(298, 13))
    assert s.value() == 1000


def test_slider_drag_follows_the_pointer_and_releases(host, qapp):
    s = GlassSlider(Qt.Horizontal, host)
    s.setRange(0, 100)
    s.setFixedSize(300, 26)
    s.show()
    qapp.processEvents()
    QTest.mousePress(s, Qt.LeftButton, Qt.NoModifier, QPoint(50, 13))
    assert s.isSliderDown()
    QTest.mouseMove(s, QPoint(250, 13))
    assert s.value() > 70
    QTest.mouseRelease(s, Qt.LeftButton, Qt.NoModifier, QPoint(250, 13))
    assert not s.isSliderDown()


def test_vertical_slider_is_zero_at_the_bottom(host, qapp):
    s = GlassSlider(Qt.Vertical, host)
    s.setRange(0, 100)
    s.setFixedSize(26, 200)
    s.show()
    qapp.processEvents()
    assert s.value_from_pos(QPointF(13, 1)) == 100
    assert s.value_from_pos(QPointF(13, 199)) == 0
    assert 40 <= s.value_from_pos(QPointF(13, 100)) <= 60


def test_slider_snaps_to_its_step(host, qapp):
    s = GlassSlider(Qt.Horizontal, host, snap_step=5)
    s.setRange(25, 300)
    s.setFixedSize(300, 26)
    s.show()
    qapp.processEvents()
    for x in range(0, 300, 7):
        assert s.value_from_pos(QPointF(x, 13)) % 5 == 0


def test_slider_handle_is_drawn_at_the_value(host, qapp):
    s = GlassSlider(Qt.Horizontal, host)
    s.setRange(0, 100)
    s.setFixedSize(300, 26)
    s.show()
    s.setValue(0)
    left = _render(s)
    s.setValue(100)
    right = _render(s)
    white = lambda img, x: _luma(img.pixelColor(x, 13)) > 230
    assert white(left, 9) and not white(left, 290)
    assert white(right, 290) and not white(right, 9)


def test_slider_handle_grows_and_the_press_halo_appears(host, pump):
    s = GlassSlider(Qt.Horizontal, host)
    s.setFixedSize(300, 26)
    s.show()
    s._stop_tweens()
    s._hover = 0.0                      # the real cursor may be over the widget: start from rest
    assert s.handle_diameter() == glass_slider.HANDLE
    s._animate("hover", 1.0, 40)
    assert pump(lambda: s._hover > 0.99, timeout=1.0)
    assert s.handle_diameter() == glass_slider.HANDLE_HOVER


# --- pills and flat buttons -------------------------------------------------

def test_pill_width_follows_its_text(host):
    b = GlassButton(host, "pill", 30, text_px=13)
    b.setText("1x")
    short = b.width()
    b.setText("재생 속도 안내")
    assert b.width() > short
    assert b.height() == 30


def test_active_pill_is_lit_with_a_white_rim(host, qapp, pump):
    b = GlassButton(host, "pill", 36, width=54, text_px=13)
    b.setText("1.5x")
    b.show()
    qapp.processEvents()
    rest = _render(b)
    b.setActive(True)
    assert pump(lambda: b._act > 0.99, timeout=1.0)
    lit = _render(b)
    assert _luma(lit.pixelColor(27, 18)) > _luma(rest.pixelColor(27, 18)) + 8
    assert b.isActive()
    b.setActive(False)
    assert pump(lambda: b._act < 0.01, timeout=1.0)


def test_flat_close_button_turns_red_on_hover(host, qapp, pump):
    b = GlassButton(host, "flat", 28, icon_px=12, radius=8, danger=True)
    b.show()
    qapp.processEvents()
    px = lambda: _render(b).pixelColor(14, 14)
    assert px().red() < 60
    b._animate("hover", 1.0, 40)
    assert pump(lambda: b._hover > 0.99, timeout=1.0)
    c = px()
    assert c.red() > 180 and c.green() < 80 and c.blue() < 90


def test_flat_button_with_a_resting_base_is_visible_at_rest(host, qapp):
    b = GlassButton(host, "flat", 16, icon_px=8, radius=8, danger=True, base=(200, 200, 200, 255))
    b.show()
    qapp.processEvents()
    assert _luma(_render(b).pixelColor(8, 8)) > 150


# --- panel ------------------------------------------------------------------

def test_glass_panel_is_dark_enough_to_read_text_and_has_a_lit_rim(qapp):
    img = QImage(200, 120, QImage.Format_ARGB32)
    img.fill(QColor(235, 235, 235))                 # a bright video frame behind the panel
    p = QPainter(img)
    paint_glass_panel(p, QRectF(0, 0, 200, 120), 18)
    p.end()
    middle = img.pixelColor(100, 60)
    assert _luma(middle) < 90, "text must stay readable over a bright picture"
    assert _luma(img.pixelColor(100, 1)) > _luma(middle) + 40, "the top rim is a light line"
    assert img.pixelColor(0, 0) == QColor(235, 235, 235), "the rounded corner leaves the picture untouched"


# --- the screens built from them ---------------------------------------------

def test_title_bar_buttons_are_animated_glass(window):
    tb = window.title_bar
    for b in (tb.btn_min, tb.btn_max, tb.btn_close, tb.btn_pip):
        assert isinstance(b, GlassButton), b
    assert tb.btn_close._danger and not tb.btn_min._danger
    assert tb.btn_pip.text() == "PIP"


def test_pip_badge_lights_up_while_pip_is_on(window, pump):
    tb = window.title_bar
    tb.set_pip_active(True)
    assert tb.btn_pip.property("active") == "true"
    assert pump(lambda: tb.btn_pip._act > 0.99, timeout=1.0)
    tb.set_pip_active(False)
    assert pump(lambda: tb.btn_pip._act < 0.01, timeout=1.0)


def test_speed_panel_uses_glass_pieces(window):
    sp = window.speed_popup
    assert isinstance(sp.slider, GlassSlider) and sp.slider.snap_step == 5
    assert isinstance(sp.btn_reset, GlassButton) and isinstance(sp.btn_pin, GlassButton)
    chips = [c for c in sp.preset_container.findChildren(GlassButton) if c.kind == "pill"]
    assert len(chips) == len(sp.presets)


def test_speed_chip_for_the_current_speed_is_the_lit_one(window):
    sp = window.speed_popup
    sp.set_current_speed(1.5)
    lit = [c for c in sp.preset_container.findChildren(GlassButton) if c.kind == "pill" and c.isActive()]
    assert [c.speed for c in lit] == [1.5]


def test_controller_speed_button_is_a_glass_pill_that_keeps_its_text(window):
    b = window.controller.btn_speed
    assert isinstance(b, GlassButton) and b.kind == "pill"
    window.controller.set_speed_display(1.4)
    assert b.text() == "1.40x"
    assert b.width() >= 50


def test_info_panel_buttons_and_slider_widgets_are_glass(window):
    ip = window.info_panel
    assert isinstance(ip.btn_copy, GlassButton) and isinstance(ip.btn_close, GlassButton)
    assert isinstance(window.controller.timeline, GlassSlider)
    assert isinstance(window.controller.volume_popup.slider, GlassSlider)


def test_panels_leave_no_stylesheet_background_behind(window):
    """The panels paint their own glass; a leftover QSS background would draw a flat box over it."""
    for w in (window.speed_popup, window.controller.volume_popup, window.info_panel):
        assert "background-color" not in w.styleSheet().replace("background-color: transparent", "")
        assert "border-radius" not in w.styleSheet()


# --- colour restraint: only the speed pill and the PIP badge carry serenity ----

def test_slider_fill_and_halo_are_white_not_serenity(host, qapp):
    assert (glass_slider.FILL_COLOR.red(), glass_slider.FILL_COLOR.green(), glass_slider.FILL_COLOR.blue()) == (255, 255, 255)
    assert (glass_slider.HALO_COLOR.red(), glass_slider.HALO_COLOR.green(), glass_slider.HALO_COLOR.blue()) == (255, 255, 255)
    s = GlassSlider(Qt.Horizontal, host)
    s.setRange(0, 100)
    s.setFixedSize(300, 26)
    s.show()
    s.setValue(60)
    c = _render(s).pixelColor(60, 13)                 # inside the filled part
    assert abs(c.red() - c.green()) < 12 and abs(c.green() - c.blue()) < 12, "filled track must be neutral"


def test_only_the_pip_badge_uses_the_serenity_rim(window):
    tb = window.title_bar
    assert tb.btn_pip._tint is True
    assert glass_button.ACTIVE_RIM == (255, 255, 255)
    for chip in window.speed_popup.preset_container.findChildren(GlassButton):
        assert chip._tint is False
    assert window.controller.btn_speed._accent_text is True      # the speed pill keeps its pale serenity text
    assert not any(b._accent_text for b in (tb.btn_pip, window.speed_popup.btn_reset, window.info_panel.btn_copy))


def test_overlay_progress_line_is_white():
    from ui import overlay
    c = overlay.PROGRESS_COLOR
    assert (c.red(), c.green(), c.blue()) == (255, 255, 255)


def test_speed_pill_text_is_bold_so_it_reads_on_the_scrim(window):
    from PySide6.QtGui import QFont
    f = window.controller.btn_speed.font()
    assert f.weight() >= QFont.Bold and f.pixelSize() >= 14
    chip = GlassButton(window, "pill", 30, text_px=12)
    assert chip.font().weight() < QFont.Bold, "only the speed pill is bold"


# --- the big play symbol shown while paused ----------------------------------

def test_center_badge_is_the_same_glass_disc_as_the_play_button(window, qapp):
    from ui.overlay import CenterBadge
    b = window.center_badge
    assert isinstance(b, CenterBadge)
    assert b.testAttribute(Qt.WA_TransparentForMouseEvents), "clicks must still reach the video"
    # it draws the cached disc that GlassButton uses (same pixmap object for the same size)
    assert glass_button.glass_disc_pixmap(b.DISC, b.MARGIN, 1.0) is glass_button.glass_disc_pixmap(b.DISC, b.MARGIN, 1.0)
    assert b.width() == b.DISC + 2 * b.MARGIN


def test_center_badge_fades_and_grows_in_then_fades_out(window, sample_video, pump):
    b = window.center_badge
    window.load_media_file(sample_video)
    assert pump(lambda: window.engine._time_pos > 0.2, timeout=3.0)
    window.engine.pause()
    assert pump(lambda: b.isVisible(), timeout=1.0)
    assert pump(lambda: b._vis > 0.99, timeout=1.5)
    window.engine.play()
    assert pump(lambda: not b.isVisible(), timeout=1.5)
    assert b._vis <= 0.01


def test_center_badge_draws_nothing_at_zero_and_something_at_full_visibility(qapp):
    from ui.overlay import CenterBadge
    host = QWidget()
    host.resize(300, 300)
    b = CenterBadge(host)
    host.show()
    b.setVisible(True)

    def painted(vis):
        b._vis = vis
        img = QImage(b.size(), QImage.Format_ARGB32)
        img.fill(QColor(120, 120, 120))
        q = QPainter(img)
        b.render(q, QPoint(0, 0), QRegion(), QWidget.RenderFlag.DrawChildren)    # no window background
        q.end()
        return sum(1 for x in range(0, b.width(), 3) for y in range(0, b.height(), 3)
                   if abs(_luma(img.pixelColor(x, y)) - 120) > 6)
    assert painted(0.0) == 0
    half, full = painted(0.5), painted(1.0)
    assert full > 100 and half > 0


def test_dark_glass_disc_is_darker_than_the_light_one(qapp):
    light = glass_button.glass_disc_pixmap(88, 14, 1.0).toImage()
    dark = glass_button.glass_disc_pixmap(88, 14, 1.0, dark=True).toImage()
    c = 14 + 44

    def over_white(img, x, y):                              # composite on white so alpha counts
        px = img.pixelColor(x, y)
        a = px.alphaF()
        return 255 * (1 - a) + 0.299 * px.red() * a + 0.587 * px.green() * a + 0.114 * px.blue() * a
    assert over_white(dark, c, c) < over_white(light, c, c) - 60
    assert dark.pixelColor(c, c).alpha() > light.pixelColor(c, c).alpha()


def test_center_badge_shows_pause_while_paused_and_play_after_resuming(window, sample_video, pump):
    b = window.center_badge
    window.load_media_file(sample_video)
    assert pump(lambda: window.engine._time_pos > 0.3, timeout=3.0)
    assert b.armed and not b.isVisible(), "nothing flashes when a file just starts playing"
    window.engine.pause()
    assert pump(lambda: b.isVisible() and b._mode == "pause", timeout=1.5)
    assert pump(lambda: b._vis > 0.99, timeout=1.5)
    assert pump(lambda: not b.isVisible(), timeout=2.5), "the PAUSE symbol fades out after the same moment"
    window.engine.play()                                     # resuming after the pause symbol is long gone
    assert pump(lambda: b.isVisible() and b._mode == "play", timeout=1.5), "a resume still shows PLAY"
    assert pump(lambda: not b.isVisible(), timeout=2.5)


def test_center_badge_play_symbol_after_resuming_while_the_pause_symbol_is_still_up(window, sample_video, pump):
    b = window.center_badge
    window.load_media_file(sample_video)
    assert pump(lambda: window.engine._time_pos > 0.3, timeout=3.0)
    window.engine.pause()
    assert pump(lambda: b.isVisible() and b._mode == "pause", timeout=1.5)
    window.engine.play()
    assert pump(lambda: b._mode == "play", timeout=1.5), "resuming swaps the symbol to PLAY"
    assert pump(lambda: not b.isVisible(), timeout=2.5), "the PLAY symbol fades out too"


def test_center_badge_ignores_the_pause_of_loading_a_file(qapp):
    from ui.overlay import CenterBadge
    host = QWidget()
    host.resize(300, 300)
    host.show()
    b = CenterBadge(host)
    b.reset()
    b.set_playing(False, True)                      # the pause that comes with loading
    assert not b.isVisible()
    b.arm()
    b.set_playing(False, True)
    assert b.isVisible()


def test_center_badge_pause_again_during_the_play_flash_goes_back_to_pause(qapp, pump):
    from ui.overlay import CenterBadge
    host = QWidget()
    host.resize(300, 300)
    host.show()
    b = CenterBadge(host)
    b.arm()
    b.set_playing(False, True)
    pump(lambda: b._vis > 0.99, timeout=1.0)
    b.set_playing(True, True)
    assert b._mode == "play"
    b.set_playing(False, True)
    assert b._mode == "pause" and b._hold.isActive(), "the hold time restarts for the pause symbol"
    assert pump(lambda: not b.isVisible(), timeout=2.5)


def test_center_badge_shows_play_after_a_resume_but_not_for_a_fresh_start(qapp, pump):
    from ui.overlay import CenterBadge
    host = QWidget()
    host.resize(300, 300)
    host.show()
    b = CenterBadge(host)
    b.reset()
    b.set_playing(True, True)                       # a file that just started playing
    assert not b.isVisible()
    b.set_playing(False, True)                      # user pauses
    assert pump(lambda: not b.isVisible() or b._vis > 0.99, timeout=1.0)
    assert pump(lambda: not b.isVisible(), timeout=2.5)
    b.set_playing(True, True)                       # user resumes after the symbol is gone
    assert b.isVisible() and b._mode == "play"
