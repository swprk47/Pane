"""
Builds the Pane logo files from the accent in styles/palette.py:

    assets/pane_logo.svg   the logo (vector, source of truth)
    assets/pane_256.png    256px preview
    assets/pane.ico        multi-size Windows icon (16..256, PNG-compressed entries)

Run after changing the accent:   python tools/make_icons.py
Design: two tinted glass panes (the big one carries a white play triangle), no
background tile, so the icon sits on any taskbar. A thin dark hairline under the
white rim keeps the glass visible on light backgrounds. See PROGRESS.md.
"""
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from styles.palette import LOGO_ACCENT, LOGO_ACCENT_LIGHT  # noqa: E402

ICO_SIZES = (16, 20, 24, 32, 40, 48, 64, 128, 256)

# geometry (100x100 viewBox): no tile, the panes fill the canvas; divider at 60 %
X0, Y0, X1, Y1, R = 4, 15, 96, 85, 18
DIV = X0 + (X1 - X0) * 0.60
GAP, R_IN = 5, 6
TRI = "23.5,38.5 43,50 23.5,61.5"
EDGE = "#22364D"                    # dark slate-blue hairline / shadow color


def build_svg(accent: str = LOGO_ACCENT, accent_light: str = LOGO_ACCENT_LIGHT) -> str:
    lx, rx = DIV - GAP / 2, DIV + GAP / 2
    left = (f"M{X0 + R} {Y0} H{lx - R_IN} Q{lx} {Y0} {lx} {Y0 + R_IN} V{Y1 - R_IN} Q{lx} {Y1} {lx - R_IN} {Y1} "
            f"H{X0 + R} A{R} {R} 0 0 1 {X0} {Y1 - R} V{Y0 + R} A{R} {R} 0 0 1 {X0 + R} {Y0} Z")
    right = (f"M{rx + R_IN} {Y0} H{X1 - R} A{R} {R} 0 0 1 {X1} {Y0 + R} V{Y1 - R} A{R} {R} 0 0 1 {X1 - R} {Y1} "
             f"H{rx + R_IN} Q{rx} {Y1} {rx} {Y1 - R_IN} V{Y0 + R_IN} Q{rx} {Y0} {rx + R_IN} {Y0} Z")

    def pane(path):
        # dark hairline UNDER the white rim: the glass stays visible on light backgrounds too
        return (f'<path d="{path}" fill="url(#glass)"/>'
                f'<path d="{path}" fill="none" stroke="{EDGE}" stroke-opacity="0.55" stroke-width="3.6" stroke-linejoin="round"/>'
                f'<path d="{path}" fill="none" stroke="url(#rim)" stroke-width="1.9" stroke-linejoin="round"/>')

    gloss = (f'<path d="M{X0} 54 C{X0} 32 19 {Y0} 36 {Y0} H55 C36 30 25 46 {X0 + 7} 74 C{X0 + 2} 70 {X0} 64 {X0} 54 Z" '
             'fill="#FFFFFF" fill-opacity="0.34" clip-path="url(#leftClip)"/>')
    # dark outline + soft drop under the white triangle: it must read on pale glass over light backgrounds
    shadow = (f'<polygon points="{TRI}" transform="translate(0 1.2)" fill="{EDGE}" fill-opacity="0.5" stroke="{EDGE}" stroke-opacity="0.5" stroke-width="7" stroke-linejoin="round"/>')
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="256" height="256" viewBox="0 0 100 100">
<defs>
<linearGradient id="glass" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="{accent_light}" stop-opacity="0.78"/><stop offset="1" stop-color="{accent}" stop-opacity="0.55"/></linearGradient>
<linearGradient id="rim" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#FFFFFF" stop-opacity="0.98"/><stop offset="0.55" stop-color="#FFFFFF" stop-opacity="0.6"/><stop offset="1" stop-color="#FFFFFF" stop-opacity="0.45"/></linearGradient>
<clipPath id="leftClip"><path d="{left}"/></clipPath>
</defs>
{pane(left)}{gloss}{pane(right)}
{shadow}<polygon points="{TRI}" fill="#FFFFFF" stroke="#FFFFFF" stroke-width="5" stroke-linejoin="round"/>
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
    svg = build_svg()
    (out / "pane_logo.svg").write_text(svg, encoding="utf-8")
    pngs = {s: render_png_bytes(svg, s) for s in ICO_SIZES}
    (out / "pane_256.png").write_bytes(pngs[256])
    (out / "pane.ico").write_bytes(build_ico(pngs))
    print(f"wrote {out / 'pane_logo.svg'}, pane_256.png and pane.ico ({len(ICO_SIZES)} sizes) with logo accent {LOGO_ACCENT}")


if __name__ == "__main__":
    main()
