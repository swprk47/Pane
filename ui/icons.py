"""
Vector SVG icons with Apple SF Symbols minimalist aesthetic.
"""
from PySide6.QtGui import QIcon, QPixmap, QPainter
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtCore import Qt, QByteArray, QRectF

# Minimalist modern white SVG icons
SVG_ICONS = {
    "play": """<svg viewBox="0 0 24 24" fill="none" stroke="#FFFFFF" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <polygon points="6 3 20 12 6 21 6 3" fill="#FFFFFF"/>
    </svg>""",

    "pause": """<svg viewBox="0 0 24 24" fill="none" stroke="#FFFFFF" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <rect x="6" y="4" width="4" height="16" fill="#FFFFFF"/>
        <rect x="14" y="4" width="4" height="16" fill="#FFFFFF"/>
    </svg>""",

    "prev_frame": """<svg viewBox="0 0 24 24" fill="none" stroke="#FFFFFF" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <line x1="5" y1="4" x2="5" y2="20" stroke-width="2.5"/>
        <polygon points="19 4 8 12 19 20" fill="#FFFFFF"/>
    </svg>""",

    "next_frame": """<svg viewBox="0 0 24 24" fill="none" stroke="#FFFFFF" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <polygon points="5 4 16 12 5 20" fill="#FFFFFF"/>
        <line x1="19" y1="4" x2="19" y2="20" stroke-width="2.5"/>
    </svg>""",

    "backward_5": """<svg viewBox="0 0 24 24" fill="none" stroke="#FFFFFF" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <path d="M11 17l-5-5 5-5"/>
        <path d="M18 17l-5-5 5-5"/>
    </svg>""",

    "forward_5": """<svg viewBox="0 0 24 24" fill="none" stroke="#FFFFFF" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <path d="M13 17l5-5-5-5"/>
        <path d="M6 17l5-5-5-5"/>
    </svg>""",

    "volume_high": """<svg viewBox="0 0 24 24" fill="none" stroke="#FFFFFF" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5" fill="#FFFFFF"/>
        <path d="M15.54 8.46a5 5 0 0 1 0 7.07"/>
        <path d="M19.07 4.93a10 10 0 0 1 0 14.14"/>
    </svg>""",

    "volume_mute": """<svg viewBox="0 0 24 24" fill="none" stroke="#FFFFFF" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5" fill="#FFFFFF"/>
        <line x1="23" y1="9" x2="17" y2="15" stroke="#FF453A" stroke-width="2.5"/>
        <line x1="17" y1="9" x2="23" y2="15" stroke="#FF453A" stroke-width="2.5"/>
    </svg>""",

    "subtitle": """<svg viewBox="0 0 24 24" fill="none" stroke="#FFFFFF" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <rect x="2" y="4" width="20" height="16" rx="3"/>
        <line x1="6" y1="12" x2="10" y2="12"/>
        <line x1="14" y1="12" x2="18" y2="12"/>
        <line x1="6" y1="16" x2="18" y2="16"/>
    </svg>""",

    "screenshot": """<svg viewBox="0 0 24 24" fill="none" stroke="#FFFFFF" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z"/>
        <circle cx="12" cy="13" r="4"/>
    </svg>""",

    "fullscreen": """<svg viewBox="0 0 24 24" fill="none" stroke="#FFFFFF" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <path d="M8 3H5a2 2 0 0 0-2 2v3"/>
        <path d="M21 8V5a2 2 0 0 0-2-2h-3"/>
        <path d="M3 16v3a2 2 0 0 0 2 2h3"/>
        <path d="M16 21h3a2 2 0 0 0 2-2v-3"/>
    </svg>""",

    "exit_fullscreen": """<svg viewBox="0 0 24 24" fill="none" stroke="#FFFFFF" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <path d="M8 3v3a2 2 0 0 1-2 2H3"/>
        <path d="M21 8h-3a2 2 0 0 1-2-2V3"/>
        <path d="M3 16h3a2 2 0 0 1 2 2v3"/>
        <path d="M16 21v-3a2 2 0 0 1 2-2h3"/>
    </svg>""",

    "settings": """<svg viewBox="0 0 24 24" fill="none" stroke="#FFFFFF" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <circle cx="12" cy="12" r="3"/>
        <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"/>
    </svg>""",

    "minimize": """<svg viewBox="0 0 24 24" fill="none" stroke="#FFFFFF" stroke-width="2" stroke-linecap="round">
        <line x1="5" y1="12" x2="19" y2="12"/>
    </svg>""",

    "maximize": """<svg viewBox="0 0 24 24" fill="none" stroke="#FFFFFF" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <rect x="5" y="5" width="14" height="14" rx="2"/>
    </svg>""",

    "restore": """<svg viewBox="0 0 24 24" fill="none" stroke="#FFFFFF" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <rect x="7" y="7" width="12" height="12" rx="2"/>
        <path d="M5 15H4a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1h10a1 1 0 0 1 1 1v1"/>
    </svg>""",

    "pin": """<svg viewBox="0 0 24 24" fill="none" stroke="#FFFFFF" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <path d="M9 10.76a2 2 0 0 1-1.11 1.79l-1.78.9A2 2 0 0 0 5 15.24V16a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1v-.76a2 2 0 0 0-1.11-1.79l-1.78-.9A2 2 0 0 1 15 10.76V7a1 1 0 0 1 1-1 2 2 0 0 0 0-4H8a2 2 0 0 0 0 4 1 1 0 0 1 1 1z"/><line x1="12" y1="17" x2="12" y2="22"/>
    </svg>""",

    "pin_fill": """<svg viewBox="0 0 24 24" fill="none" stroke="#FFFFFF" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <path d="M9 10.76a2 2 0 0 1-1.11 1.79l-1.78.9A2 2 0 0 0 5 15.24V16a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1v-.76a2 2 0 0 0-1.11-1.79l-1.78-.9A2 2 0 0 1 15 10.76V7a1 1 0 0 1 1-1 2 2 0 0 0 0-4H8a2 2 0 0 0 0 4 1 1 0 0 1 1 1z" fill="#FFFFFF"/><line x1="12" y1="17" x2="12" y2="22"/>
    </svg>""",

    "speed": """<svg viewBox="0 0 24 24" fill="none" stroke="#FFFFFF" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <path d="m12 14 4-4"/><path d="M3.34 19a10 10 0 1 1 17.32 0"/>
    </svg>""",

    "clock": """<svg viewBox="0 0 24 24" fill="none" stroke="#FFFFFF" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/>
    </svg>""",

    "warning": """<svg viewBox="0 0 24 24" fill="none" stroke="#FFFFFF" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/>
    </svg>""",

    "check": """<svg viewBox="0 0 24 24" fill="none" stroke="#FFFFFF" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/>
    </svg>""",

    "pip": """<svg viewBox="0 0 24 24" fill="none" stroke="#FFFFFF" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <rect x="2" y="4" width="20" height="14" rx="2"/><rect x="12" y="10" width="8" height="5" rx="1" fill="#FFFFFF"/>
    </svg>""",

    "film": """<svg viewBox="0 0 24 24" fill="none" stroke="#FFFFFF" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <rect x="2" y="2" width="20" height="20" rx="2.18"/><line x1="7" y1="2" x2="7" y2="22"/><line x1="17" y1="2" x2="17" y2="22"/><line x1="2" y1="12" x2="22" y2="12"/><line x1="2" y1="7" x2="7" y2="7"/><line x1="2" y1="17" x2="7" y2="17"/><line x1="17" y1="17" x2="22" y2="17"/><line x1="17" y1="7" x2="22" y2="7"/>
    </svg>""",

    # --- rounded outline icons for the glass transport buttons (drawn on a 24 grid, white) ---
    "play_glass": """<svg viewBox="0 0 24 24" fill="none" stroke="#FFFFFF" stroke-width="1.7" stroke-linejoin="round">
        <path d="M8 8.3 Q8 5.5 10.41 6.93 L16.59 10.57 Q19 12 16.59 13.43 L10.41 17.07 Q8 18.5 8 15.7 Z"/>
    </svg>""",

    "pause_glass": """<svg viewBox="0 0 24 24" fill="none" stroke="#FFFFFF" stroke-width="1.7">
        <rect x="6.2" y="4.8" width="4" height="14.4" rx="2"/><rect x="13.8" y="4.8" width="4" height="14.4" rx="2"/>
    </svg>""",

    # two rounded triangles; optically centred (the flat bases carry the weight, so shift away from them)
    "backward_glass": """<svg viewBox="0 0 24 24" fill="none" stroke="#FFFFFF" stroke-width="2" stroke-linejoin="round">
        <g transform="translate(-0.4 0)"><path d="M11 8.8 Q11 6.6 9.24 7.92 L5.56 10.68 Q3.8 12 5.56 13.32 L9.24 16.08 Q11 17.4 11 15.2 Z"/><path d="M19 8.8 Q19 6.6 17.24 7.92 L13.56 10.68 Q11.8 12 13.56 13.32 L17.24 16.08 Q19 17.4 19 15.2 Z"/></g>
    </svg>""",

    "forward_glass": """<svg viewBox="0 0 24 24" fill="none" stroke="#FFFFFF" stroke-width="2" stroke-linejoin="round">
        <g transform="translate(24 0) scale(-1 1) translate(-0.4 0)"><path d="M11 8.8 Q11 6.6 9.24 7.92 L5.56 10.68 Q3.8 12 5.56 13.32 L9.24 16.08 Q11 17.4 11 15.2 Z"/><path d="M19 8.8 Q19 6.6 17.24 7.92 L13.56 10.68 Q11.8 12 13.56 13.32 L17.24 16.08 Q19 17.4 19 15.2 Z"/></g>
    </svg>""",

    "prev_frame_glass": """<svg viewBox="0 0 24 24" fill="none" stroke="#FFFFFF" stroke-width="2" stroke-linejoin="round" stroke-linecap="round">
        <path d="M6.4 6 V18"/><g transform="translate(7.4 0)"><path d="M11 8.8 Q11 6.6 9.24 7.92 L5.56 10.68 Q3.8 12 5.56 13.32 L9.24 16.08 Q11 17.4 11 15.2 Z"/></g>
    </svg>""",

    "next_frame_glass": """<svg viewBox="0 0 24 24" fill="none" stroke="#FFFFFF" stroke-width="2" stroke-linejoin="round" stroke-linecap="round">
        <path d="M17.6 6 V18"/><g transform="translate(24 0) scale(-1 1) translate(7.4 0)"><path d="M11 8.8 Q11 6.6 9.24 7.92 L5.56 10.68 Q3.8 12 5.56 13.32 L9.24 16.08 Q11 17.4 11 15.2 Z"/></g>
    </svg>""",

    "close": """<svg viewBox="0 0 24 24" fill="none" stroke="#FFFFFF" stroke-width="2" stroke-linecap="round">
        <line x1="18" y1="6" x2="6" y2="18"/>
        <line x1="6" y1="6" x2="18" y2="18"/>
    </svg>"""
}

from core.paths import ASSETS_DIR
LOGO_SVG = ASSETS_DIR / "pane_logo.svg"
LOGO_ICO = ASSETS_DIR / "pane.ico"


def get_logo_pixmap(size: int = 18) -> QPixmap:
    """The Pane logo (assets/pane_logo.svg) as a crisp pixmap."""
    pixmap = QPixmap(size * 2, size * 2)
    pixmap.fill(Qt.transparent)
    pixmap.setDevicePixelRatio(2.0)
    if LOGO_SVG.exists():
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing, True)
        QSvgRenderer(str(LOGO_SVG)).render(painter, QRectF(0, 0, size, size))
        painter.end()
    return pixmap


def get_logo_icon(size: int = 18) -> QIcon:
    return QIcon(get_logo_pixmap(size))


def get_svg_pixmap(name: str, size: int = 18, color: str = None, stroke_width: float = None) -> QPixmap:
    """Crisp pixmap (rendered at 2x, devicePixelRatio 2) for use in QLabel etc."""
    svg_data = SVG_ICONS.get(name)
    pixmap = QPixmap(size * 2, size * 2)
    pixmap.fill(Qt.transparent)
    pixmap.setDevicePixelRatio(2.0)
    if not svg_data:
        return pixmap
    if stroke_width is not None:
        svg_data = svg_data.replace('stroke-width="2"', f'stroke-width="{stroke_width}"')
    if color:
        svg_data = svg_data.replace("#FFFFFF", color)
    renderer = QSvgRenderer(QByteArray(svg_data.encode("utf-8")))
    painter = QPainter(pixmap)
    renderer.render(painter, QRectF(0, 0, size, size))
    painter.end()
    return pixmap


def get_svg_icon(name: str, size: int = 18, color: str = None) -> QIcon:
    """Render an SVG string into a crisp high-res QIcon."""
    svg_data = SVG_ICONS.get(name)
    if not svg_data:
        return QIcon()

    if color:
        svg_data = svg_data.replace("#FFFFFF", color)

    renderer = QSvgRenderer(QByteArray(svg_data.encode("utf-8")))
    pixmap = QPixmap(size * 2, size * 2)  # 2x for Retina/HighDPI
    pixmap.fill(Qt.transparent)

    painter = QPainter(pixmap)
    renderer.render(painter)
    painter.end()

    return QIcon(pixmap)
