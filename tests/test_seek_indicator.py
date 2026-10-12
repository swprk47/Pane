"""The time-seek indicator: a dark edge scrim with a chevron icon and the seconds, on the side you moved toward."""
import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QImage, QRegion
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QWidget

from ui.overlay import SeekIndicator


@pytest.fixture
def host(qapp):
    h = QWidget()
    h.resize(900, 500)
    h.show()
    qapp.processEvents()
    yield h
    h.close()


@pytest.fixture
def ind(host):
    return SeekIndicator(host)


# --- what it shows ---------------------------------------------------------

def test_it_is_invisible_until_used_so_it_costs_nothing(ind):
    assert not ind.isVisible()


def test_a_seek_shows_the_seconds_on_the_side_it_went_toward(ind):
    ind.show_seek(5)
    assert ind.isVisible() and ind.side == "right" and ind.total == 5 and ind.text == "5s"
    ind.show_seek(-5)
    assert ind.side == "left" and ind.total == 5, "the other way starts again at its own number"


def test_pressing_again_adds_up_the_seconds(ind):
    for _ in range(3):
        ind.show_seek(5)
    assert ind.total == 15 and ind.text == "15s"


def test_one_second_steps_add_up_too(ind):
    ind.show_seek(1)
    ind.show_seek(1)
    assert ind.text == "2s"
    ind.show_seek(5)
    assert ind.text == "7s"


def test_a_pause_in_pressing_starts_the_count_again(ind, pump):
    ind.show_seek(5)
    ind.show_seek(5)
    ind.HOLD_MS = 30
    ind._hold.setInterval(30)
    ind._hold.start()
    assert pump(lambda: not ind._hold.isActive(), timeout=2)
    ind.show_seek(5)
    assert ind.total == 5


def test_it_fades_away_and_is_hidden_again(ind, pump):
    ind.HOLD_MS = 30
    ind._hold.setInterval(30)
    ind.show_seek(5)
    assert pump(lambda: not ind.isVisible(), timeout=3), "a hidden widget costs no compositing"


def test_a_new_file_clears_it_at_once(ind):
    ind.show_seek(5)
    ind.reset()
    assert not ind.isVisible() and ind.total == 0


# --- where it is and how it looks --------------------------------------------------

def test_it_covers_a_third_of_the_width_at_the_edge_it_points_to(host, ind):
    ind.place(host.rect())
    ind.show_seek(5)
    assert ind.geometry().right() == host.rect().right() and ind.height() == host.height()
    assert abs(ind.width() - host.width() * 0.34) <= 2
    ind.show_seek(-5)
    ind.place(host.rect())
    assert ind.geometry().left() == 0


def render(ind) -> QImage:
    img = QImage(ind.size(), QImage.Format_ARGB32_Premultiplied)
    img.fill(0)
    ind.render(img, QPoint(), QRegion(), QWidget.RenderFlag(0))      # (grab() paints an opaque background)
    return img


def bright_pixels(img, x0, x1):
    """White-ish pixels in the columns x0..x1 around the middle of the strip (the arrows' rows)."""
    mid = img.height() // 2
    return sum(1 for y in range(mid - 16, mid + 16) for x in range(x0, x1)
               if img.pixelColor(x, y).red() > 200 and img.pixelColor(x, y).alpha() > 200)


def test_the_scrim_is_darkest_at_the_screen_edge_and_gone_inside(host, ind):
    ind.place(host.rect())
    ind.show_seek(5)
    ind._vis = 1.0
    img = render(ind)
    edge = img.pixelColor(img.width() - 2, 10).alpha()           # (away from the icon and its number)
    middle = img.pixelColor(img.width() // 2, 10).alpha()
    inner = img.pixelColor(2, 10).alpha()
    assert edge > middle > inner, (edge, middle, inner)
    assert inner <= 4 and edge >= 140


def test_it_does_not_take_the_mouse(ind):
    assert ind.testAttribute(Qt.WA_TransparentForMouseEvents)


# --- wired to the player ---------------------------------------------------------

@pytest.fixture
def playing(window, sample_video, pump):
    window.load_media_file(sample_video)
    pump(lambda: window.engine.mpv._get_property("video-format") is not None)
    return window


def test_the_arrow_keys_show_it(playing, pump):
    w = playing
    QTest.keyClick(w, Qt.Key_Right)
    assert w.seek_indicator.isVisible() and w.seek_indicator.side == "right" and w.seek_indicator.text == "5s"
    QTest.keyClick(w, Qt.Key_Right, Qt.ShiftModifier)
    assert w.seek_indicator.text == "6s", "Shift+Right is one second, added to the five"
    QTest.keyClick(w, Qt.Key_Left)
    assert w.seek_indicator.side == "left" and w.seek_indicator.text == "5s"


def test_the_seek_buttons_show_it_too(playing):
    w = playing
    w.controller.seek_backward_clicked.emit(5.0)
    assert w.seek_indicator.side == "left" and w.seek_indicator.text == "5s"


def test_it_shows_while_paused_too(playing):
    w = playing
    w.engine.pause()
    w.seek_relative(5)
    assert w.seek_indicator.isVisible()


def test_nothing_shows_when_no_video_is_loaded(window):
    window.seek_relative(5)
    assert not window.seek_indicator.isVisible()


def test_it_follows_the_window_size_and_stays_under_the_controls(playing, qapp):
    w = playing
    w.seek_relative(5)
    w.resize(1200, 700)
    qapp.processEvents()
    vp = w.viewport.geometry()
    assert w.seek_indicator.geometry().right() == vp.right()
    kids = w.central_widget.children()
    assert kids.index(w.seek_indicator) < kids.index(w.controller), "the controls draw over the shade"


def test_loading_another_file_clears_it(playing, sample_video):
    w = playing
    w.seek_relative(5)
    w.load_media_file(sample_video)
    assert not w.seek_indicator.isVisible()


# --- the arrow: one chevron first, then the second slides out from behind it --------------

def arrow_slots(ind):
    """Column ranges of the leading and the trailing chevron of the right-pointing arrow."""
    ix = ind.width() - ind.INSET - ind.ICON
    k = ind.ICON / 24.0
    return (ix + int(12.5 * k), ix + int(19 * k)), (ix + int(5.5 * k), ix + int(12 * k))


def test_the_arrow_starts_as_a_single_chevron_and_becomes_a_double(host, ind):
    ind.place(host.rect())
    ind.show_seek(5)
    ind._vis = 1.0
    lead, trail = arrow_slots(ind)
    ind._arrow = 0.0
    start = render(ind)
    ind._arrow = 1.0
    end = render(ind)
    assert bright_pixels(start, *lead) > 10 and bright_pixels(end, *lead) > 10, "the leading chevron is always there"
    assert bright_pixels(start, *trail) == 0, "the second chevron is not yet there at the start"
    assert bright_pixels(end, *trail) > 10, "and has arrived at the end"


def test_every_press_plays_the_arrow_motion_again(ind, pump):
    ind.show_seek(5)
    assert ind._arrow < 1.0, "a fresh arrow begins as a single chevron"
    assert pump(lambda: ind._arrow >= 1.0, timeout=2)
    ind.show_seek(5)
    assert ind._arrow < 1.0, "pressing again replays it"


def test_the_left_arrow_mirrors_the_right_one(host, ind):
    ind.place(host.rect())
    ind.show_seek(-5)
    ind._vis = 1.0
    ind._arrow = 0.0
    start = render(ind)
    ind._arrow = 1.0
    end = render(ind)
    ix = ind.INSET
    k = ind.ICON / 24.0
    lead, trail = (ix + int(5 * k), ix + int(11.5 * k)), (ix + int(12 * k), ix + int(18.5 * k))
    assert bright_pixels(start, *lead) > 10 and bright_pixels(start, *trail) == 0
    assert bright_pixels(end, *trail) > 10
