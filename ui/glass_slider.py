"""
Slider with the glass look: thin track that thickens, a round white handle that grows, all animated.

Used by the timeline, the volume popup and the speed panel. Click / drag set the value where the pointer
is (no page-step jumps); ``snap_step`` rounds to a step (the speed slider moves in 0.05x = 5 units).
"""
from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QColor, QPainter, QRadialGradient
from PySide6.QtWidgets import QSlider

from ui.glass_button import Tweening

TRACK = 4.0              # track thickness at rest
TRACK_HOVER = 6.5        # ... under the pointer
HANDLE = 14.0            # handle diameter at rest
HANDLE_HOVER = 17.0
HANDLE_PRESS = 15.5      # a touch smaller again while held (it feels pushed in)
GROW_MS = 160
TRACK_COLOR = QColor(255, 255, 255, 66)
HANDLE_COLOR = QColor(255, 255, 255)
HANDLE_HOVER_COLOR = QColor(240, 246, 251)
FILL_COLOR = QColor(255, 255, 255, 235)     # the played / filled part of the track: plain white
HALO_COLOR = QColor(255, 255, 255, 80)


class GlassSlider(QSlider, Tweening):
    def __init__(self, orientation=Qt.Horizontal, parent=None, snap_step: int = None):
        super().__init__(orientation, parent)
        self.snap_step = snap_step
        self._hover = 0.0
        self._press = 0.0
        self._init_tweens()
        self.setMouseTracking(True)
        self.setCursor(Qt.PointingHandCursor)
        # A slider that kept the keyboard focus after a click swallowed the arrow keys (volume, seeking) meant
        # for the window; like the buttons, sliders are mouse-only.
        self.setFocusPolicy(Qt.NoFocus)
        self._held = False

    # --- geometry -----------------------------------------------------------------------------
    def _margin(self) -> float:
        return HANDLE_HOVER / 2.0 + 1.0

    def _span(self) -> float:
        length = self.width() if self.orientation() == Qt.Horizontal else self.height()
        return max(1.0, length - 2 * self._margin())

    def value_ratio(self) -> float:
        rng = self.maximum() - self.minimum()
        return 0.0 if rng <= 0 else (self.value() - self.minimum()) / rng

    def ratio_from_pos(self, pos) -> float:
        if self.orientation() == Qt.Horizontal:
            r = (pos.x() - self._margin()) / self._span()
        else:
            r = 1.0 - (pos.y() - self._margin()) / self._span()
        return max(0.0, min(1.0, r))

    def value_from_pos(self, pos) -> int:
        v = self.minimum() + self.ratio_from_pos(pos) * (self.maximum() - self.minimum())
        if self.snap_step:
            v = round(v / self.snap_step) * self.snap_step
        return int(round(max(self.minimum(), min(self.maximum(), v))))

    def handle_diameter(self) -> float:
        base = HANDLE + (HANDLE_HOVER - HANDLE) * self._hover
        return base + (HANDLE_PRESS - HANDLE_HOVER) * self._press * self._hover

    def track_thickness(self) -> float:
        return TRACK + (TRACK_HOVER - TRACK) * self._hover

    # --- hook for a slider that adds to the track (the timeline's hover preview) ----------------
    def paint_over_track(self, p, margin: float, span: float, cy: float, thickness: float):
        """Called after the filled part and before the handle (horizontal sliders only)."""

    # --- interaction --------------------------------------------------------------------------
    def enterEvent(self, event):
        self._animate("hover", 1.0, GROW_MS)
        super().enterEvent(event)

    def leaveEvent(self, event):
        if not self._held:
            self._animate("hover", 0.0, GROW_MS)
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._held = True
            self.setSliderDown(True)
            self._animate("press", 1.0, 70)
            self._animate("hover", 1.0, GROW_MS)
            self.setValue(self.value_from_pos(event.position()))
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._held:
            self.setValue(self.value_from_pos(event.position()))
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self._held:
            self._held = False
            self.setSliderDown(False)
            self._animate("press", 0.0, 220)
            if not self.underMouse():
                self._animate("hover", 0.0, GROW_MS)
            event.accept()
        else:
            super().mouseReleaseEvent(event)

    def hideEvent(self, event):
        self._stop_tweens()
        self._hover = self._press = 0.0
        self._held = False
        super().hideEvent(event)

    # --- painting -----------------------------------------------------------------------------
    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        horizontal = self.orientation() == Qt.Horizontal
        t = self.track_thickness()
        m, span = self._margin(), self._span()
        ratio = self.value_ratio()
        cx, cy = self.width() / 2.0, self.height() / 2.0
        if horizontal:
            groove = QRectF(m, cy - t / 2, span, t)
            hx, hy = m + ratio * span, cy
            fill = QRectF(m, cy - t / 2, ratio * span, t)
        else:
            groove = QRectF(cx - t / 2, m, t, span)
            hx, hy = cx, m + (1.0 - ratio) * span
            fill = QRectF(cx - t / 2, hy, t, (ratio) * span)
        p.setPen(Qt.NoPen)
        p.setBrush(TRACK_COLOR)
        p.drawRoundedRect(groove, t / 2, t / 2)
        if self.isEnabled() and ratio > 0:
            p.setBrush(FILL_COLOR)
            p.drawRoundedRect(fill, t / 2, t / 2)
        if horizontal:
            self.paint_over_track(p, m, span, cy, t)
        d = self.handle_diameter()
        # soft shadow under the handle, a halo while held, then the handle itself
        sh = QRadialGradient(hx, hy + 1.5, d * 0.9)
        sh.setColorAt(0.0, QColor(10, 15, 30, 90))
        sh.setColorAt(1.0, QColor(10, 15, 30, 0))
        p.setBrush(sh)
        p.drawEllipse(QRectF(hx - d, hy + 1.5 - d, 2 * d, 2 * d))
        if self._press > 0:
            halo = QColor(HALO_COLOR)
            halo.setAlpha(int(HALO_COLOR.alpha() * self._press))
            p.setBrush(halo)
            r = d / 2 + 5 * self._press
            p.drawEllipse(QRectF(hx - r, hy - r, 2 * r, 2 * r))
        mix = self._hover
        col = QColor(int(HANDLE_COLOR.red() + (HANDLE_HOVER_COLOR.red() - HANDLE_COLOR.red()) * mix),
                     int(HANDLE_COLOR.green() + (HANDLE_HOVER_COLOR.green() - HANDLE_COLOR.green()) * mix),
                     int(HANDLE_COLOR.blue() + (HANDLE_HOVER_COLOR.blue() - HANDLE_COLOR.blue()) * mix))
        p.setBrush(col)
        p.drawEllipse(QRectF(hx - d / 2, hy - d / 2, d, d))
