"""
Small mouse-transparent widgets drawn over the video: the top scrim with the
file name, the thin progress line shown while the controls are hidden, and the
big play badge shown while paused.
"""
from PySide6.QtWidgets import QWidget, QGraphicsOpacityEffect
from PySide6.QtCore import Qt, QRectF, QPointF
from PySide6.QtGui import (
    QPainter, QLinearGradient, QColor, QFont, QFontMetrics, QPen, QPolygonF
)

from styles.palette import ACCENT as _ACCENT_HEX

ACCENT = QColor(_ACCENT_HEX)


class _OverlayBase(QWidget):
    def __init__(self, parent):
        super().__init__(parent)
        # Clicks fall through to the video viewport (drag, double-click, menu).
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)


class TopScrim(_OverlayBase):
    """Dark gradient at the top edge with the media title on it."""
    HEIGHT = 110

    def __init__(self, parent):
        super().__init__(parent)
        self._title = ""
        self.setFixedHeight(self.HEIGHT)
        self._fx = QGraphicsOpacityEffect(self)
        self._fx.setOpacity(1.0)
        self.setGraphicsEffect(self._fx)

    def set_title(self, title: str):
        self._title = title
        self.update()

    def set_opacity(self, value: float):
        self._fx.setOpacity(max(0.0, min(1.0, value)))

    def paintEvent(self, event):
        p = QPainter(self)
        g = QLinearGradient(0, 0, 0, self.height())
        g.setColorAt(0.0, QColor(0, 0, 0, 150))
        g.setColorAt(1.0, QColor(0, 0, 0, 0))
        p.fillRect(self.rect(), g)
        if self._title:
            font = QFont("Segoe UI Variable Text", 11)
            font.setWeight(QFont.DemiBold)
            p.setFont(font)
            text = QFontMetrics(font).elidedText(self._title, Qt.ElideRight, self.width() - 48)
            p.setPen(QColor(0, 0, 0, 120))          # soft shadow
            p.drawText(25, 29, text)
            p.setPen(QColor(255, 255, 255, 240))
            p.drawText(24, 28, text)


class MiniProgress(_OverlayBase):
    """3px progress line at the bottom edge, visible while controls are hidden."""
    def __init__(self, parent):
        super().__init__(parent)
        self._ratio = 0.0
        self.setFixedHeight(3)

    def set_ratio(self, ratio: float):
        self._ratio = max(0.0, min(1.0, ratio))
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(255, 255, 255, 56))
        p.fillRect(0, 0, int(self.width() * self._ratio), self.height(), ACCENT)


class CenterBadge(_OverlayBase):
    """Large translucent play symbol shown in the middle while paused."""
    SIZE = 92

    def __init__(self, parent):
        super().__init__(parent)
        self.setFixedSize(self.SIZE, self.SIZE)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        r = QRectF(1, 1, self.width() - 2, self.height() - 2)
        p.setBrush(QColor(20, 20, 28, 128))
        p.setPen(QPen(QColor(255, 255, 255, 102), 1))
        p.drawEllipse(r)
        c = r.center()
        s = 21
        tri = QPolygonF([QPointF(c.x() - s * 0.55, c.y() - s), QPointF(c.x() + s * 0.95, c.y()),
                         QPointF(c.x() - s * 0.55, c.y() + s)])
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(255, 255, 255))
        p.drawPolygon(tri)
