"""Logo files, app icon wiring and the app accent palette."""
import re
import struct
from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QImage

from styles import palette
from tools import make_icons
from ui.icons import LOGO_ICO, LOGO_SVG, get_logo_pixmap

ROOT = Path(__file__).resolve().parent.parent
SOURCE_DIRS = ("ui", "styles", "core")


def _sources():
    for d in SOURCE_DIRS:
        for p in (ROOT / d).glob("*.py"):
            if p.name != "palette.py":
                yield p
    yield ROOT / "main.py"


# --- palette ---------------------------------------------------------------

def test_palette_rgb_matches_hex():
    for hex_value, rgb in ((palette.ACCENT, palette.ACCENT_RGB), (palette.ACCENT_LIGHT, palette.ACCENT_LIGHT_RGB)):
        c = QColor(hex_value)
        assert f"{c.red()}, {c.green()}, {c.blue()}" == rgb


def test_accent_is_serenity():
    assert palette.ACCENT.upper() == "#B3CEE5"


def test_logo_colors_are_independent_of_the_app_accent():
    """The logo (blue-violet slab) has its own colors; the UI accent must not leak into the generator."""
    assert not hasattr(palette, "LOGO_ACCENT")
    svg = make_icons.build_svg().upper()
    assert palette.ACCENT.upper() not in svg and palette.ACCENT_LIGHT.upper() not in svg


def _contrast(a, b):
    def lum(hex_value):
        c = QColor(hex_value)
        f = lambda v: v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
        return 0.2126 * f(c.redF()) + 0.7152 * f(c.greenF()) + 0.0722 * f(c.blueF())
    hi, lo = sorted((lum(a), lum(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def test_accent_is_readable_on_the_dark_ui():
    assert _contrast(palette.ACCENT, "#16161C") >= 7.0          # progress / speed text on dark
    assert _contrast(palette.ACCENT_LIGHT, "#16161C") >= 7.0


def test_text_on_a_solid_accent_fill_is_dark():
    """White on a pale accent is unreadable (selected menu item, save button, active PIP badge)."""
    assert _contrast(palette.ON_ACCENT, palette.ACCENT) >= 7.0
    assert _contrast("#FFFFFF", palette.ACCENT) < 3.0
    for rel in ("ui/title_bar.py", "ui/main_window.py", "ui/glass_controller.py"):
        assert palette.ON_ACCENT.lower() in (ROOT / rel).read_text(encoding="utf-8").lower(), rel


def test_no_legacy_blue_left_in_source():
    """After the accent change from blue to violet, no old blue literal may remain."""
    offenders = []
    for path in _sources():
        text = path.read_text(encoding="utf-8")
        for lit in palette.LEGACY_ACCENT_LITERALS:
            if re.search(re.escape(lit), text, flags=re.I):
                offenders.append(f"{path.relative_to(ROOT)}: {lit}")
    assert not offenders, "\n".join(offenders)


def test_accent_is_actually_used_in_the_theme():
    from styles.glass_theme import GLASS_THEME_QSS
    assert palette.ACCENT_RGB in GLASS_THEME_QSS


# --- logo files ------------------------------------------------------------

def test_logo_assets_exist():
    for p in (LOGO_SVG, LOGO_ICO, ROOT / "assets" / "pane_256.png"):
        assert p.exists() and p.stat().st_size > 500, p


def test_logo_svg_uses_the_logo_colors():
    svg = LOGO_SVG.read_text(encoding="utf-8").upper()
    for color in (make_icons.SLAB_LOW[0], make_icons.SLAB_LOW[1], make_icons.TRI_FILL[0], make_icons.OUTLINE):
        assert color.upper() in svg, color


def test_checked_in_logo_matches_the_generator():
    """Fails when tools/make_icons.py changed but was not re-run."""
    assert LOGO_SVG.read_text(encoding="utf-8") == make_icons.build_svg()


def test_ico_contains_all_sizes():
    data = LOGO_ICO.read_bytes()
    reserved, kind, count = struct.unpack("<HHH", data[:6])
    assert (reserved, kind) == (0, 1)
    assert count == len(make_icons.ICO_SIZES)
    sizes = []
    for i in range(count):
        w, h, _c, _r, _planes, bpp, length, offset = struct.unpack("<BBBBHHII", data[6 + 16 * i:22 + 16 * i])
        sizes.append(w or 256)
        assert data[offset:offset + 8] == b"\x89PNG\r\n\x1a\n", "entries are PNG-compressed"
        assert bpp == 32 and length > 0
    assert sizes == sorted(make_icons.ICO_SIZES)


def test_rendered_logo_is_not_blank(qapp):
    img = get_logo_pixmap(64).toImage()
    assert img.width() == 128                                   # rendered at 2x for crispness
    visible = sum(1 for x in range(0, 128, 4) for y in range(0, 128, 4) if img.pixelColor(x, y).alpha() > 100)
    assert visible > 400, "logo renders (nearly) empty"


def _alpha_grid(img, step=2):
    return [[img.pixelColor(x, y).alpha() for x in range(0, img.width(), step)] for y in range(0, img.height(), step)]


def test_logo_is_a_rounded_slab_with_transparent_corners(qapp):
    """A rounded square plate: corners are cut away, the plate itself is opaque."""
    img = get_logo_pixmap(64).toImage()                         # 128 px
    for x, y in ((1, 1), (126, 1), (1, 126), (126, 126)):
        assert img.pixelColor(x, y).alpha() < 40, f"({x},{y}) should be transparent"
    for x, y in ((64, 20), (30, 60), (100, 60)):
        assert img.pixelColor(x, y).alpha() > 240, f"({x},{y}) should be opaque slab"


def test_logo_fills_the_canvas(qapp):
    img = get_logo_pixmap(64).toImage()
    cols = [x for x in range(128) if any(img.pixelColor(x, y).alpha() > 100 for y in range(0, 128, 2))]
    rows = [y for y in range(128) if any(img.pixelColor(x, y).alpha() > 100 for x in range(0, 128, 2))]
    assert (cols[-1] - cols[0]) / 128 >= 0.85, "the slab should fill the icon width"
    assert (rows[-1] - rows[0]) / 128 >= 0.85, "the slab should fill the icon height"


def test_small_drawing_widens_the_gap_and_enlarges_the_triangle():
    large, small = make_icons.build_svg(), make_icons.build_svg(small=True)
    assert large != small
    assert make_icons.SMALL["pane"].split()[2] == "H43" and make_icons.LARGE["pane"].split()[2] == "H46"
    assert make_icons.SMALL["tri"] == "M27 31 L48.5 47 L27 63 Z" and make_icons.LARGE["tri"] == "M27 32 L50 47 L27 62 Z"
    assert 'H43 A12' in small and 'H46 A12' in large


def test_ico_uses_the_small_drawing_up_to_32px_only(qapp):
    from PySide6.QtGui import QImage
    data = LOGO_ICO.read_bytes()
    count = struct.unpack("<H", data[4:6])[0]
    by_size = {}
    for i in range(count):
        w, _h, _c, _r, _p, _b, length, offset = struct.unpack("<BBBBHHII", data[6 + 16 * i:22 + 16 * i])
        by_size[w or 256] = data[offset:offset + length]
    for size, png in by_size.items():
        svg = make_icons.build_svg(small=size <= make_icons.SMALL_MAX)
        assert png == make_icons.render_png_bytes(svg, size), f"{size}px entry is not the expected drawing"
    assert make_icons.SMALL_MAX == 32


def test_logo_light_line_is_a_rect_with_height():
    """A horizontal line with a bbox gradient does not render: the lower light must be a rect."""
    for small in (False, True):
        svg = make_icons.build_svg(small=small)
        assert '<rect' in svg and 'fill="url(#line)"' in svg


def test_small_logo_keeps_the_gap_and_the_triangle(qapp):
    """At 16 px the play triangle (white) and the gap between the panes must still be there."""
    img = QImage.fromData(make_icons.render_png_bytes(make_icons.build_svg(small=True), 16))
    def white(x, y):
        c = img.pixelColor(x, y)
        return c.alpha() > 200 and c.red() > 225 and c.green() > 225 and c.blue() > 225
    assert sum(white(x, y) for x in range(16) for y in range(16)) >= 6, "white triangle vanished at 16 px"


# --- app wiring ------------------------------------------------------------

def test_title_bar_shows_the_logo(window):
    icon = window.title_bar.logo_btn.icon()
    assert not icon.isNull()
    assert icon.cacheKey() != 0


def test_main_sets_window_icon_and_app_id():
    src = (ROOT / "main.py").read_text(encoding="utf-8")
    assert "setWindowIcon" in src and "AppUserModelID" in src and "LOGO_ICO" in src
