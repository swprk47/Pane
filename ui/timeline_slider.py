from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QMouseEvent

from ui.glass_slider import GlassSlider


class TimelineSlider(GlassSlider):
    """
    Glass-styled hover-responsive timeline seek bar (drawn by GlassSlider: thin track that thickens and a
    round white handle that grows on hover). Supports click-to-seek and drag-to-seek.
    """
    seek_requested = Signal(float)  # Requested position in seconds

    def __init__(self, parent=None):
        super().__init__(Qt.Horizontal, parent)
        self.setRange(0, 1000)
        self.setValue(0)
        self.setFixedHeight(26)         # room for the grown handle and its press halo

        self._duration = 0.0
        self._is_dragging = False

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

    def _emit_seek(self):
        if self._duration > 0:
            self.seek_requested.emit(self.value_ratio() * self._duration)

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton:
            self._is_dragging = True
            super().mousePressEvent(event)           # sets the value under the pointer
            self._emit_seek()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent):
        if self._is_dragging:
            super().mouseMoveEvent(event)
            self._emit_seek()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton:
            self._is_dragging = False
            self.setValue(self.value_from_pos(event.position()))
            self._emit_seek()
            super().mouseReleaseEvent(event)
        else:
            super().mouseReleaseEvent(event)
