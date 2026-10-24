"""Bookmark pins and chapter gaps on the seek bar: drawn for real (render), never grab() (it paints an opaque background)."""
import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QImage, QRegion
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QWidget

from ui.timeline_slider import PIN_COLOR, TimelineSlider

DURATION = 3860.0
WIDTH = 900


def make_slider(qapp, host):
    s = TimelineSlider(host)
    s.setGeometry(0, 20, WIDTH, 26)
    s.set_duration(DURATION)
    return s


@pytest.fixture
def host(qapp):
    h = QWidget()
    h.resize(WIDTH, 80)
    h.show()
    qapp.processEvents()
    yield h
    h.close()


@pytest.fixture
def slider(qapp, host):
    s = make_slider(qapp, host)
    qapp.processEvents()
    return s


def render(s) -> QImage:
    img = QImage(s.size(), QImage.Format_ARGB32_Premultiplied)
    img.fill(0)
    s.render(img, QPoint(), QRegion(), QWidget.RenderFlag(0))
    return img


def x_of(s, seconds):
    return s._margin() + seconds / DURATION * s._span()


def alpha(img, x, y):
    return img.pixelColor(int(x), int(y)).alpha()


def coverage(img, y, x0, x1):
    """How many pixels wide the paint is along row y (the sum of the coverage: a pin at a fractional x is partly in two pixels)."""
    return sum(alpha(img, x, y) for x in range(x0, x1)) / 255.0


def transparent_runs(img, y, x0=12, x1=888):
    """The runs of fully transparent pixels along row y between x0 and x1 (the gaps of the groove)."""
    runs, start = [], None
    for x in range(x0, x1):
        clear = alpha(img, x, y) == 0
        if clear and start is None:
            start = x
        if not clear and start is not None:
            runs.append((start, x - start))
            start = None
    if start is not None:
        runs.append((start, x1 - start))
    return runs


# --- nothing to draw: nothing changes ----------------------------------------------------------------------------------

def test_without_marks_the_bar_paints_exactly_as_before(qapp, host, slider):
    plain = render(slider)
    other = QWidget(host)
    other.setGeometry(0, 20, WIDTH, 26)
    marked = make_slider(qapp, other)
    marked.set_marks([], [])
    marked.set_chapters_visible(True)
    assert render(marked) == plain


def test_chapters_switched_off_or_too_many_paint_exactly_as_before(qapp, host, slider):
    plain = render(slider)
    slider.set_marks([], [760.0, 1800.0])
    slider.set_chapters_visible(False)
    assert render(slider) == plain, "switched off"
    slider.set_chapters_visible(True)
    slider.set_marks([], [i * 50.0 for i in range(70)])
    assert render(slider) == plain, "70 chapters: too many for gaps"


# --- chapter gaps ---------------------------------------------------------------------------------------------------

def test_a_chapter_gap_is_not_painted_at_all_and_its_neighbours_are(slider):
    slider.set_marks([], [0.0, 760.0, 1800.0])
    img = render(slider)
    cy = slider.height() // 2
    runs = transparent_runs(img, cy)
    assert len(runs) == 2, runs                                             # none for the chapter at 0
    start, width = runs[0]
    assert width == 2 and abs(start + 1 - x_of(slider, 760.0)) <= 1.5
    assert alpha(img, start - 2, cy) > 0 and alpha(img, start + width + 1, cy) > 0, "the groove goes on at both sides"


def test_the_gap_cuts_the_played_part_too(slider):
    slider.set_marks([], [0.0, 760.0])
    slider.set_time_pos(2000.0)
    img = render(slider)
    cy = slider.height() // 2
    runs = transparent_runs(img, cy)
    assert len(runs) == 1 and runs[0][1] == 2
    assert alpha(img, runs[0][0] - 3, cy) > 200, "the played part (white) is right next to it"


def test_the_gap_is_wider_while_the_bar_is_hovered(slider):
    slider.set_marks([], [0.0, 760.0])
    slider._hover = 1.0
    runs = transparent_runs(render(slider), slider.height() // 2)
    assert len(runs) == 1 and runs[0][1] == 3


def test_a_gap_that_would_touch_the_previous_one_is_skipped(slider):
    slider.set_marks([], [0.0, 760.0, 761.0, 1800.0])
    assert len(transparent_runs(render(slider), slider.height() // 2)) == 2


# --- bookmark pins -------------------------------------------------------------------------------------------------------

def test_a_pin_is_amber_four_by_eighteen_and_bigger_near_the_pointer(slider):
    slider.set_marks([1800.0], [])
    cx, cy = int(round(x_of(slider, 1800.0))), slider.height() // 2
    img = render(slider)
    c = img.pixelColor(cx, cy - 7)
    assert (c.red(), c.green(), c.blue(), c.alpha()) == (PIN_COLOR.red(), PIN_COLOR.green(), PIN_COLOR.blue(), 255)
    assert abs(coverage(img, cy - 7, cx - 8, cx + 9) - 4.0) < 0.3, "4 px wide"
    assert alpha(img, cx, cy - 9) > 0 and alpha(img, cx, cy - 10) == 0, "18 px tall"
    slider._hover_ratio = 1800.0 / DURATION                                     # the pointer is on it
    near = render(slider)
    assert alpha(near, cx, cy - 11) > 0, "24 px tall near the pointer"
    assert coverage(near, cy - 7, cx - 8, cx + 9) > 5.0, "5 px wide plus the outline"


def test_a_pin_at_the_very_start_or_end_stays_inside_the_bar(slider):
    slider.set_marks([0.0, DURATION], [])
    slider.set_time_pos(2000.0)                      # (the handle, and its shadow, away from the two pins)
    img = render(slider)
    cy = slider.height() // 2
    for seconds in (0.0, DURATION):
        cx = int(round(x_of(slider, seconds)))
        assert abs(coverage(img, cy - 7, cx - 8, cx + 9) - 4.0) < 0.3, "the whole pin is inside the bar's widget"
    assert alpha(img, 1, cy - 7) == 0 and alpha(img, WIDTH - 2, cy - 7) == 0


def test_a_bookmark_beyond_the_length_is_not_drawn(qapp, host, slider):
    plain = render(slider)
    slider.set_marks([DURATION + 100.0], [])
    assert render(slider) == plain
    assert slider.pin_at(x_of(slider, DURATION)) is None


def test_pin_at_finds_the_pin_within_six_pixels(slider):
    slider.set_marks([1800.0, 2400.0], [])
    x = x_of(slider, 1800.0)
    assert slider.pin_at(x) == 1800.0 and slider.pin_at(x + 5.5) == 1800.0
    assert slider.pin_at(x + 8) is None


def test_pressing_a_pin_emits_pin_pressed_and_does_not_move_the_handle(slider):
    slider.set_marks([1800.0], [])
    slider.set_time_pos(100.0)
    before = slider.value()
    pins, seeks = [], []
    slider.pin_pressed.connect(pins.append)
    slider.seek_requested.connect(seeks.append)
    cy = slider.height() // 2
    QTest.mouseClick(slider, Qt.LeftButton, Qt.NoModifier, QPoint(int(round(x_of(slider, 1800.0))), cy))
    assert pins == [1800.0] and seeks == [] and slider.value() == before, "press and release both leave the handle alone"


def test_pressing_elsewhere_still_seeks_as_before(slider):
    slider.set_marks([1800.0], [])
    pins, seeks = [], []
    slider.pin_pressed.connect(pins.append)
    slider.seek_requested.connect(seeks.append)
    QTest.mouseClick(slider, Qt.LeftButton, Qt.NoModifier, QPoint(int(x_of(slider, 500.0)), slider.height() // 2))
    assert pins == [] and seeks and abs(seeks[-1] - 500.0) < 10.0


def test_each_chapter_is_a_rounded_bar_so_the_gap_is_wider_toward_the_edges_of_the_bar(slider):
    slider.set_marks([], [0.0, 760.0, 1800.0])
    img = render(slider)
    cy = slider.height() / 2.0
    t = slider.track_thickness()
    top_row, mid_row = int(cy - t / 2.0), int(cy)
    centre = int(round(x_of(slider, 760.0)))
    lo, hi = centre - 8, centre + 8

    def missing(row):
        """How many pixels of the bar are missing around the gap on this row (a full bar there would be 16 wide)."""
        full = alpha(img, centre - 30, row) / 255.0
        return 16 * full - coverage(img, row, lo, hi)

    assert abs(missing(mid_row) - 2.0 * alpha(img, centre - 30, mid_row) / 255.0) < 0.8, "about 2 px where the bar is fullest"
    assert missing(top_row) > missing(mid_row) + 0.3, "the ends of the neighbouring bars are rounded off"
