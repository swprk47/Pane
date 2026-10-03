"""
Builds the Pane logo files:

    assets/pane_logo.svg   the logo (vector, source of truth; large-size drawing)
    assets/pane_256.png    256px preview
    assets/pane.ico        multi-size Windows icon (16..256, PNG-compressed entries)

Run after changing the design:   python tools/make_icons.py
Design (design "Q"): a thick glass slab (blue-violet) carrying two glass panes, the big one with a
white play triangle, and a thin light line along the lower edge. The logo has its own colors (below);
the app's UI accent in styles/palette.py is independent of it. Sizes up to 32 px use a slightly
different drawing (narrower big pane = wider gap, bigger triangle, heavier lines) so the gap and the
triangle still read; 48 px and up use the large drawing. See PROGRESS.md.
"""
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

ICO_SIZES = (16, 20, 24, 32, 40, 48, 64, 128, 256)
SMALL_MAX = 32                      # ICO entries up to this size use the small-size drawing

# ---- logo colors (independent of the app accent)
SLAB_LOW = ("#7B6BE6", "#453CB4")                           # lower layer, vertical, opaque
SLAB_TOP = (("#6FA0F2", 0), ("#6376E8", 0.5), ("#8D62E4", 1))   # top face, diagonal
SLAB_TOP_OPACITY = 0.97
PANE_FILL = (("#FFFFFF", 0.40), ("#CFC8FF", 0.20))          # panes, diagonal
TRI_FILL = ("#FFFFFF", "#EEF0FF")
LINE_STOPS = (("#DCCBFF", 0, 0.0), ("#EADCF8", 0.18, 0.85), ("#FFEADD", 0.5, 0.95),
              ("#EADCF8", 0.82, 0.85), ("#DCCBFF", 1, 0.0))  # lower light line, horizontal, transparent ends
RIM_STOPS = (0, 1.0), (0.5, 0.35), (1, 0.7)                 # white rim light opacity along the diagonal
OUTLINE = "#0F0E4A"
TRI_SHADOW = "#101456"

# ---- geometry (100x100 viewBox)
SLAB_LOW_PATH = "M27 9 H73 A22 22 0 0 1 95 31 V75 A22 22 0 0 1 73 97 H27 A22 22 0 0 1 5 75 V31 A22 22 0 0 1 27 9 Z"
SLAB_TOP_PATH = "M27 3 H73 A22 22 0 0 1 95 25 V69 A22 22 0 0 1 73 91 H27 A22 22 0 0 1 5 69 V25 A22 22 0 0 1 27 3 Z"
PILL_PATH = "M75 15 A11 11 0 0 1 86 26 V68 A11 11 0 0 1 75 79 A11 11 0 0 1 64 68 V26 A11 11 0 0 1 75 15 Z"

# values that differ between the large and the small drawing
LARGE = dict(
    pane="M26 15 H46 A12 12 0 0 1 58 27 V67 A12 12 0 0 1 46 79 H26 A12 12 0 0 1 14 67 V27 A12 12 0 0 1 26 15 Z",
    tri="M27 32 L50 47 L27 62 Z",
    low=(0.35, 2), top=(0.22, 2.4), panel=(0.30, 2.2),
    rim_top=1.6, rim_panel=1.4,
    tri_dy=1.3, tri_shadow_opacity=0.36, tri_shadow_w=7, tri_w=5,
    line=(26, 93.4, 48, 3.2, 1.6),
)
SMALL = dict(
    pane="M26 15 H43 A12 12 0 0 1 55 27 V67 A12 12 0 0 1 43 79 H26 A12 12 0 0 1 14 67 V27 A12 12 0 0 1 26 15 Z",
    tri="M27 31 L48.5 47 L27 63 Z",
    low=(0.4, 2.2), top=(0.26, 2.6), panel=(0.34, 2.6),
    rim_top=1.8, rim_panel=1.6,
    tri_dy=1.4, tri_shadow_opacity=0.38, tri_shadow_w=7.5, tri_w=5.5,
    line=(24, 92.2, 52, 4.2, 2.1),
)


def build_svg(small: bool = False) -> str:
    g = SMALL if small else LARGE

    def outline(path, opacity, width):
        return (f'<path d="{path}" fill="none" stroke="{OUTLINE}" stroke-opacity="{opacity}" '
                f'stroke-width="{width}" stroke-linejoin="round"/>')

    def rim(path, width):
        return f'<path d="{path}" fill="none" stroke="url(#rim)" stroke-width="{width}" stroke-linejoin="round"/>'

    def panel(path):
        return f'<path d="{path}" fill="url(#pane)"/>' + outline(path, *g["panel"]) + rim(path, g["rim_panel"])

    lx, ly, lw, lh, lr = g["line"]
    top_stops = "".join(f'<stop offset="{o}" stop-color="{c}"/>' for c, o in SLAB_TOP)
    pane_stops = "".join(f'<stop offset="{o}" stop-color="{c}" stop-opacity="{a}"/>'
                         for o, (c, a) in zip((0, 1), PANE_FILL))
    line_stops = "".join(f'<stop offset="{o}" stop-color="{c}" stop-opacity="{a}"/>' for c, o, a in LINE_STOPS)
    rim_stops = "".join(f'<stop offset="{o}" stop-color="#FFFFFF" stop-opacity="{a}"/>' for o, a in RIM_STOPS)
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="256" height="256" viewBox="0 0 100 100">
<defs>
<linearGradient id="low" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{SLAB_LOW[0]}"/><stop offset="1" stop-color="{SLAB_LOW[1]}"/></linearGradient>
<linearGradient id="top" x1="0" y1="0" x2="1" y2="1">{top_stops}</linearGradient>
<linearGradient id="pane" x1="0" y1="0" x2="1" y2="1">{pane_stops}</linearGradient>
<linearGradient id="tri" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="{TRI_FILL[0]}"/><stop offset="1" stop-color="{TRI_FILL[1]}"/></linearGradient>
<linearGradient id="line" x1="0" y1="0" x2="1" y2="0">{line_stops}</linearGradient>
<linearGradient id="rim" x1="0" y1="0" x2="1" y2="1">{rim_stops}</linearGradient>
</defs>
<path d="{SLAB_LOW_PATH}" fill="url(#low)"/>{outline(SLAB_LOW_PATH, *g["low"])}
<rect x="{lx}" y="{ly}" width="{lw}" height="{lh}" rx="{lr}" fill="url(#line)"/>
<path d="{SLAB_TOP_PATH}" fill="url(#top)" fill-opacity="{SLAB_TOP_OPACITY}"/>{outline(SLAB_TOP_PATH, *g["top"])}{rim(SLAB_TOP_PATH, g["rim_top"])}
{panel(g["pane"])}{panel(PILL_PATH)}
<path d="{g["tri"]}" transform="translate(0 {g["tri_dy"]})" fill="{TRI_SHADOW}" fill-opacity="{g["tri_shadow_opacity"]}" stroke="{TRI_SHADOW}" stroke-opacity="{g["tri_shadow_opacity"]}" stroke-width="{g["tri_shadow_w"]}" stroke-linejoin="round"/>
<path d="{g["tri"]}" fill="url(#tri)" stroke="url(#tri)" stroke-width="{g["tri_w"]}" stroke-linejoin="round"/>
</svg>
'''


def render_png_bytes(svg: str, size: int) -> bytes:
    from PySide6.QtCore import QBuffer, QByteArray, QIODevice, Qt
    from PySide6.QtGui import QImage, QPainter
    from PySide6.QtSvg import QSvgRenderer

    renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))
    image = QImage(size, size, QImage.Format_ARGB32)
    image.fill(Qt.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.Antialiasing, True)
    renderer.render(painter)
    painter.end()
    buf = QBuffer()
    buf.open(QIODevice.WriteOnly)
    image.save(buf, "PNG")
    return bytes(buf.data())


def build_ico(pngs: dict) -> bytes:
    """ICO container with PNG-compressed entries (supported since Windows Vista)."""
    sizes = sorted(pngs)
    header = struct.pack("<HHH", 0, 1, len(sizes))
    entries, blobs = b"", b""
    offset = 6 + 16 * len(sizes)
    for size in sizes:
        data = pngs[size]
        dim = 0 if size >= 256 else size
        entries += struct.pack("<BBBBHHII", dim, dim, 0, 0, 1, 32, len(data), offset)
        blobs += data
        offset += len(data)
    return header + entries + blobs


def main():
    from PySide6.QtGui import QGuiApplication
    app = QGuiApplication.instance() or QGuiApplication([])  # noqa: F841  (needed for QImage/QPainter fonts)

    out = ROOT / "assets"
    out.mkdir(exist_ok=True)
    large, small = build_svg(), build_svg(small=True)
    (out / "pane_logo.svg").write_text(large, encoding="utf-8")
    pngs = {s: render_png_bytes(small if s <= SMALL_MAX else large, s) for s in ICO_SIZES}
    (out / "pane_256.png").write_bytes(pngs[256])
    (out / "pane.ico").write_bytes(build_ico(pngs))
    print(f"wrote {out / 'pane_logo.svg'}, pane_256.png and pane.ico ({len(ICO_SIZES)} sizes)")


if __name__ == "__main__":
    main()
