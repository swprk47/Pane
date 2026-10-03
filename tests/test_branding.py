"""Logo files, app icon wiring and the violet accent palette."""
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


def test_accent_is_serenity_and_the_logo_shares_it():
    assert palette.ACCENT.upper() == "#B3CEE5"
    assert palette.LOGO_ACCENT == palette.ACCENT
    assert palette.LOGO_ACCENT_LIGHT == palette.ACCENT_LIGHT


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


def test_logo_svg_uses_the_logo_accent():
    svg = LOGO_SVG.read_text(encoding="utf-8")
    assert palette.LOGO_ACCENT in svg and palette.LOGO_ACCENT_LIGHT in svg


def test_checked_in_logo_matches_the_generator():
    """Fails when the palette changed but tools/make_icons.py was not re-run."""
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


def test_logo_has_no_background_tile(qapp):
    """The icon is the glass panes alone (no square), so it blends into any taskbar."""
    img = get_logo_pixmap(64).toImage()
    for x, y in ((1, 1), (126, 1), (1, 126), (126, 126), (64, 1), (64, 126), (1, 64)):
        assert img.pixelColor(x, y).alpha() < 40, f"({x},{y}) is not transparent"


def test_logo_fills_the_canvas_width(qapp):
    img = get_logo_pixmap(64).toImage()
    cols = [x for x in range(128) if any(img.pixelColor(x, y).alpha() > 100 for y in range(0, 128, 2))]
    assert (cols[-1] - cols[0]) / 128 >= 0.85, "panes should fill the icon so it is not tiny in the taskbar"


# --- app wiring ------------------------------------------------------------

def test_title_bar_shows_the_logo(window):
    icon = window.title_bar.logo_btn.icon()
    assert not icon.isNull()
    assert icon.cacheKey() != 0


def test_main_sets_window_icon_and_app_id():
    src = (ROOT / "main.py").read_text(encoding="utf-8")
    assert "setWindowIcon" in src and "AppUserModelID" in src and "LOGO_ICO" in src
