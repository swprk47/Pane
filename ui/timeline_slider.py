from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QColor, QMouseEvent

from ui.glass_slider import GlassSlider


PREVIEW_COLOR = QColor(255, 255, 255, 110)      # the part from the handle to the pointer (only ahead of the handle)
MARKER_COLOR = QColor(255, 255, 255, 245)       # its end: as thick as the (hovered) track, no taller
MARKER_WIDTH = 2.0


class TimelineSlider(GlassSlider):
    """
    Glass-styled hover-responsive timeline seek bar (drawn by GlassSlider: thin track that thickens and a
    round white handle that grows on hover). Supports click-to-seek and drag-to-seek.
    """
    seek_requested = Signal(float)  # Requested position in seconds
    hover_moved = Signal(float, float)   # time under the pointer (or the one being dragged to), its x in this widget
    hover_left = Signal()                # the pointer left the bar (not while a drag goes on)

    def __init__(self, parent=None):
        super().__init__(Qt.Horizontal, parent)
        self.setRange(0, 1000)
        self.setValue(0)
        self.setFixedHeight(26)         # room for the grown handle and its press halo

        self._duration = 0.0
        self._is_dragging = False
        self._hover_ratio = None         # where the pointer is on the bar (0..1) while it is over it, else None

    def set_duration(self, duration: float):
        self._duration = max(0.0, float(duration))

    def set_time_pos(self, time_pos: float):
        """Update slider position from playback progress (only when not dragging)."""
        if self._is_dragging or self._duration <= 0.0:
            return
        ratio = max(0.0, min(1.0, time_pos / self._duration))
        self.blockSignals(True)
        self.setValue(int(ratio * 1000))
        self.blockSignals(False)
        self.update()

    # --- hover preview --------------------------------------------------------------------------
    def _preview_ratio(self):
        if self._hover_ratio is None or self._is_dragging or self._duration <= 0:
            return None
        return self._hover_ratio

    def paint_over_track(self, p, margin, span, cy, thickness):
        h = self._preview_ratio()
        if h is None:
            return
        r = self.value_ratio()
        if h <= r:
            return                                  # behind the handle: what was played keeps its colour
        x0, x1 = margin + r * span, margin + h * span
        p.setPen(Qt.NoPen)
        p.setBrush(PREVIEW_COLOR)
        p.drawRect(QRectF(x0, cy - thickness / 2, x1 - x0, thickness))
        p.setBrush(MARKER_COLOR)
        p.drawRoundedRect(QRectF(margin + h * span - MARKER_WIDTH / 2, cy - thickness / 2, MARKER_WIDTH, thickness),
                          MARKER_WIDTH / 2, MARKER_WIDTH / 2)

    def _report_hover(self, ratio: float):
        self._hover_ratio = ratio
        if self._duration > 0:
            self.hover_moved.emit(ratio * self._duration, self._margin() + ratio * self._span())
        self.update()

    def leaveEvent(self, event):
        self._hover_ratio = None
        if not self._is_dragging:
            self.hover_left.emit()
        self.update()
        super().leaveEvent(event)

    def hideEvent(self, event):
        self._hover_ratio = None
        self.hover_left.emit()
        super().hideEvent(event)

    def _emit_seek(self):
        if self._duration > 0:
            self.seek_requested.emit(self.value_ratio() * self._duration)

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton:
            self._is_dragging = True
            super().mousePressEvent(event)           # sets the value under the pointer
            self._emit_seek()
            self._report_hover(self.value_ratio())
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent):
        if self._is_dragging:
            super().mouseMoveEvent(event)
            self._emit_seek()
            self._report_hover(self.value_ratio())
        else:
            super().mouseMoveEvent(event)
            self._report_hover(self.ratio_from_pos(event.position()))

    def mouseReleaseEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton:
            self._is_dragging = False
            self.setValue(self.value_from_pos(event.position()))
            self._emit_seek()
            super().mouseReleaseEvent(event)
            if not self.underMouse():
                self._hover_ratio = None
                self.hover_left.emit()
            self.update()
        else:
            super().mouseReleaseEvent(event)
