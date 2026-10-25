"""
The shortcut help panel: the keys (in groups), the mouse gestures and a few tips, read from ``ui.help_content``.
Two layouts: ``CENTERED`` (two columns over a dimmed window, modal; for the home screen) and ``DRAWER`` (one column at the
right edge, the video stays visible; for a playing video). The body scrolls when it does not fit, with a soft fade at the
edge that has more to see. The panel only draws and sizes itself: ``ui.help_flow.HelpFlow`` decides when and which.
"""
from PySide6.QtCore import QRect, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QLinearGradient, QPainter
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QScrollArea, QVBoxLayout, QWidget

from ui.glass_button import paint_glass_panel
from ui.help_content import KEY_GROUPS, MOUSE, TIPS

FONT = '"Segoe UI Variable Text", "Segoe UI", sans-serif'
BODY = QColor(11, 13, 19, 242)                 # almost opaque: the first mock let the logo show through
DIM = QColor(0, 0, 0, 215)
RADIUS = 18
PAD = 22
FADE_HEIGHT = 26

CENTER_MAX = (900, 640)
CENTER_SIDE = 80                               # room taken from the area's width (40 each side)
CENTER_VERTICAL = 92                           # ... and from its height (46 above and below)
DRAWER_WIDTH = 420
DRAWER_RIGHT = 14
DRAWER_TOP = 46
DRAWER_BOTTOM = 14
DRAWER_MAX_HEIGHT = 640

CHIP_QSS = (f'QLabel {{ background: rgba(255, 255, 255, 0.16); border: 1px solid rgba(255, 255, 255, 0.26); border-radius: 6px;'
            f' padding: 3px 9px; color: #FFFFFF; font-family: {FONT}; font-size: 13px; font-weight: 700; }}')
SCROLL_QSS = ('QScrollArea { background: transparent; border: none; } QScrollArea > QWidget > QWidget { background: transparent; }'
              ' QScrollBar:vertical { background: transparent; width: 6px; margin: 2px; }'
              ' QScrollBar::handle:vertical { background: rgba(255, 255, 255, 0.25); border-radius: 2px; min-height: 24px; }'
              ' QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }'
              ' QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }')

LEFT_GROUPS = ("재생", "소리 · 자막", "북마크")
CHIP_COLUMN = {"재생": 190, "소리 · 자막": 190, "북마크": 190, "화면 · 파일": 150}
MOUSE_COLUMN = 110
DRAWER_COLUMN = 185


def _text(text: str, px: int, color: str, bold=False, name="", wrap=True) -> QLabel:
    lbl = QLabel(text)
    if name:
        lbl.setObjectName(name)
    lbl.setWordWrap(wrap)
    lbl.setFocusPolicy(Qt.NoFocus)
    lbl.setStyleSheet(f'QLabel {{ background: transparent; color: {color}; font-family: {FONT}; font-size: {px}px;'
                      f' font-weight: {700 if bold else 400}; }}')
    return lbl


def _group_title(text: str) -> QLabel:
    lbl = _text(text, 13, "#9FC5FF", bold=True, wrap=False)
    lbl.setContentsMargins(0, 8, 0, 2)
    return lbl


def _key_row(chips, description: str, column: int) -> QWidget:
    row = QWidget()
    lay = QHBoxLayout(row)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(10)
    box = QWidget()
    box.setFixedWidth(column)
    box_lay = QHBoxLayout(box)
    box_lay.setContentsMargins(0, 0, 0, 0)
    box_lay.setSpacing(4)
    for chip in chips:
        c = QLabel(chip)
        c.setObjectName("KeyChip")
        c.setStyleSheet(CHIP_QSS)
        box_lay.addWidget(c)
    box_lay.addStretch()
    lay.addWidget(box, 0, Qt.AlignTop)
    lay.addWidget(_text(description, 14, "rgba(255, 255, 255, 0.92)"), 1)
    return row


def _mouse_row(gesture: str, description: str, column: int) -> QWidget:
    row = QWidget()
    lay = QHBoxLayout(row)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(10)
    g = _text(gesture, 13, "rgba(255, 255, 255, 0.78)", bold=True, name="MouseGesture")
    g.setFixedWidth(column)
    lay.addWidget(g, 0, Qt.AlignTop)
    lay.addWidget(_text(description, 14, "rgba(255, 255, 255, 0.92)"), 1)
    return row


class _Dim(QWidget):
    """Darkens the window behind the centred panel and swallows the mouse; a press asks the panel to close."""

    pressed = Signal()

    def __init__(self, parent):
        super().__init__(parent)
        self.setFocusPolicy(Qt.NoFocus)
        self.clear = False                     # (after the help closed: still there to absorb a double click, but invisible)
        self.hide()

    def paintEvent(self, event):
        if not self.clear:
            QPainter(self).fillRect(self.rect(), DIM)

    def mousePressEvent(self, event):
        event.accept()
        self.pressed.emit()

    def mouseReleaseEvent(self, event):
        event.accept()

    def mouseDoubleClickEvent(self, event):
        event.accept()

    def wheelEvent(self, event):
        event.accept()

    def contextMenuEvent(self, event):
        event.accept()


class _Fade(QWidget):
    """A soft gradient over the edge of the scroll area that has more to see (``top``: fades downward from the top edge)."""

    def __init__(self, parent, top: bool):
        super().__init__(parent)
        self._top = top
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.hide()

    def paintEvent(self, event):
        p = QPainter(self)
        g = QLinearGradient(0, 0, 0, self.height())
        solid, clear = QColor(BODY), QColor(BODY)
        clear.setAlpha(0)
        g.setColorAt(0, solid if self._top else clear)
        g.setColorAt(1, clear if self._top else solid)
        p.fillRect(self.rect(), g)


class HelpPanel(QFrame):
    CENTERED = "centered"
    DRAWER = "drawer"

    close_requested = Signal()                 # a click on the dim

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self._kind = ""
        self._open = False
        self._built_kind = ""
        self.setFocusPolicy(Qt.NoFocus)
        self.setAttribute(Qt.WA_StyledBackground, False)
        self._dim = _Dim(parent)
        self._dim.pressed.connect(self.close_requested.emit)
        self._dim.stackUnder(self)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(PAD, 16, PAD - 6, 14)
        outer.setSpacing(6)
        header = QHBoxLayout()
        header.addWidget(_text("단축키와 사용법", 16, "#FFFFFF", bold=True, wrap=False))
        header.addStretch()
        header.addWidget(_text("Esc 로 닫기", 12, "rgba(255, 255, 255, 0.5)", wrap=False))
        outer.addLayout(header)

        self.scroll_area = QScrollArea(self)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.NoFrame)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll_area.setStyleSheet(SCROLL_QSS)
        for part in (self.scroll_area, self.scroll_area.viewport(), self.scroll_area.verticalScrollBar()):
            part.setFocusPolicy(Qt.NoFocus)    # (a click must not hand the focus over: the scroll area eats the arrow keys)
        outer.addWidget(self.scroll_area, 1)

        self._fade_top_w = _Fade(self, top=True)
        self._fade_bottom_w = _Fade(self, top=False)
        bar = self.scroll_area.verticalScrollBar()
        bar.valueChanged.connect(self._update_fades)
        bar.rangeChanged.connect(self._update_fades)
        self.hide()

    # --- state --------------------------------------------------------------------------------------------------------

    @property
    def kind(self) -> str:
        return self._kind

    def is_open(self) -> bool:
        return self._open

    def fade_top(self) -> bool:
        return self.scroll_area.verticalScrollBar().value() > 0

    def fade_bottom(self) -> bool:
        bar = self.scroll_area.verticalScrollBar()
        return bar.value() < bar.maximum()

    # --- showing ------------------------------------------------------------------------------------------------------

    def show_as(self, kind: str, area: QRect) -> None:
        """Build the body for ``kind`` (once per change), size and place the panel inside ``area``, show it (and the dim)."""
        if kind not in (self.CENTERED, self.DRAWER):
            raise ValueError(kind)
        self._kind = kind
        if self._built_kind != kind:
            self.scroll_area.setWidget(self._build_body(kind))
            self._built_kind = kind
        self._open = True
        self._place(area)
        parent = self.parentWidget()
        if kind == self.CENTERED:
            self._dim.clear = False
            self._dim.setGeometry(parent.rect())
            self._dim.show()
            self._dim.update()
            self._dim.raise_()
        else:
            self._dim.hide()
        self.show()
        self.raise_()
        self._update_fades()

    def hide_help(self, absorb_ms: int = 0) -> None:
        """Close. ``absorb_ms``: keep the (now invisible) dim for that long, so the second click of a double click that
        closed the help does not land on the video below it."""
        self._open = False
        self.hide()
        if absorb_ms > 0 and self._dim.isVisible():
            self._dim.clear = True
            self._dim.update()
            QTimer.singleShot(absorb_ms, self._end_absorb)
        else:
            self._dim.hide()
        self._update_fades()

    def _end_absorb(self) -> None:
        if not self._open and self._dim.clear:
            self._dim.hide()

    def raise_dim(self) -> None:
        self._dim.raise_()

    def _place(self, area: QRect) -> None:
        if self._kind == self.CENTERED:
            w = max(200, min(CENTER_MAX[0], area.width() - CENTER_SIDE))
            h = max(120, min(CENTER_MAX[1], area.height() - CENTER_VERTICAL))
            self.setGeometry(area.x() + (area.width() - w) // 2, area.y() + (area.height() - h) // 2, w, h)
        else:
            w = min(DRAWER_WIDTH, area.width() - 2 * DRAWER_RIGHT)
            h = min(DRAWER_MAX_HEIGHT, area.height() - DRAWER_TOP - DRAWER_BOTTOM)
            self.setGeometry(area.right() + 1 - DRAWER_RIGHT - w, area.y() + DRAWER_TOP, w, max(80, h))
        self._place_fades()

    def _place_fades(self) -> None:
        sa = self.scroll_area.geometry()
        self._fade_top_w.setGeometry(sa.x(), sa.y(), sa.width(), FADE_HEIGHT)
        self._fade_bottom_w.setGeometry(sa.x(), sa.bottom() + 1 - FADE_HEIGHT, sa.width(), FADE_HEIGHT)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._place_fades()
        self._update_fades()

    def _update_fades(self, *_):
        top = self._open and self.fade_top()
        bottom = self._open and self.fade_bottom()
        self._fade_top_w.setVisible(top)
        self._fade_bottom_w.setVisible(bottom)
        if top:
            self._fade_top_w.raise_()
        if bottom:
            self._fade_bottom_w.raise_()

    # --- the body -----------------------------------------------------------------------------------------------------

    def _group(self, title: str, column_for_keys: int) -> QVBoxLayout:
        lay = QVBoxLayout()
        lay.setSpacing(5)
        lay.addWidget(_group_title(title))
        rows = dict(KEY_GROUPS)[title]
        for chips, description in rows:
            lay.addWidget(_key_row(chips, description, column_for_keys))
        return lay

    def _mouse(self, column: int) -> QVBoxLayout:
        lay = QVBoxLayout()
        lay.setSpacing(5)
        lay.addWidget(_group_title("마우스"))
        for gesture, description in MOUSE:
            lay.addWidget(_mouse_row(gesture, description, column))
        return lay

    def _tips(self) -> QVBoxLayout:
        lay = QVBoxLayout()
        lay.setSpacing(6)
        lay.addWidget(_group_title("팁"))
        for tip in TIPS:
            lay.addWidget(_text(tip, 13, "rgba(255, 255, 255, 0.88)", name="TipText"))
        return lay

    def _build_body(self, kind: str) -> QWidget:
        body = QWidget()
        if kind == self.CENTERED:
            root = QHBoxLayout(body)
            root.setContentsMargins(0, 0, 14, 0)
            root.setSpacing(36)
            left, right = QVBoxLayout(), QVBoxLayout()
            for title, _rows in KEY_GROUPS:
                if title in LEFT_GROUPS:
                    left.addLayout(self._group(title, CHIP_COLUMN[title]))
            right.addLayout(self._group("화면 · 파일", CHIP_COLUMN["화면 · 파일"]))
            right.addLayout(self._mouse(MOUSE_COLUMN))
            right.addLayout(self._tips())
            for col in (left, right):
                col.addStretch()
            root.addLayout(left, 1)
            root.addLayout(right, 1)
        else:
            root = QVBoxLayout(body)
            root.setContentsMargins(0, 0, 14, 8)
            root.setSpacing(0)
            for title, _rows in KEY_GROUPS:
                root.addLayout(self._group(title, DRAWER_COLUMN))
            root.addLayout(self._mouse(DRAWER_COLUMN))
            root.addLayout(self._tips())
            root.addStretch()
        return body

    # --- painting and the mouse ---------------------------------------------------------------------------------------

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        p.setBrush(BODY)
        p.drawRoundedRect(QRectF(self.rect()), RADIUS, RADIUS)
        paint_glass_panel(p, QRectF(self.rect()), RADIUS, calm=True)

    def mousePressEvent(self, event):          # the panel is solid: a click on it never reaches the video below
        event.accept()

    def mouseReleaseEvent(self, event):
        event.accept()

    def mouseDoubleClickEvent(self, event):
        event.accept()

    def wheelEvent(self, event):
        event.accept()

    def contextMenuEvent(self, event):
        event.accept()
