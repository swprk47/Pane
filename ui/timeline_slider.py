from PySide6.QtWidgets import QSlider, QWidget
from PySide6.QtCore import Qt, Signal, QPoint
from PySide6.QtGui import QMouseEvent

class TimelineSlider(QSlider):
    """
    Apple Glass-styled hover-responsive timeline seek bar.
    Expands on hover and supports click-to-seek and drag-to-seek.
    """
    seek_requested = Signal(float)  # Requested position in seconds

    def __init__(self, parent=None):
        super().__init__(Qt.Horizontal, parent)
        self.setRange(0, 1000)
        self.setValue(0)
        self.setFixedHeight(22)
        self.setCursor(Qt.PointingHandCursor)
        self.setMouseTracking(True)

        self._duration = 0.0
        self._is_dragging = False

        self._apply_style()

    def _apply_style(self):
        # Thick rounded track with a glass-pill thumb.
        # Thin track that thickens on hover, accent-colored thumb dot.
        self.setStyleSheet("""
            QSlider::groove:horizontal {
                height: 5px;
                background: rgba(255, 255, 255, 0.26);
                border-radius: 2px;
            }
            QSlider::groove:horizontal:hover {
                height: 7px;
                border-radius: 3px;
            }
            QSlider::sub-page:horizontal {
                background: #0A84FF;
                border-radius: 2px;
            }
            QSlider::handle:horizontal {
                background: #0A84FF;
                border: 3px solid rgba(10, 132, 255, 0.35);
                width: 10px;
                height: 10px;
                margin-top: -7px;
                margin-bottom: -7px;
                border-radius: 8px;
            }
            QSlider::handle:horizontal:hover {
                background: #3D9BFF;
            }
        """)

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

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton:
            self._is_dragging = True
            pos_ratio = event.position().x() / self.width()
            pos_ratio = max(0.0, min(1.0, pos_ratio))
            self.setValue(int(pos_ratio * 1000))
            if self._duration > 0:
                self.seek_requested.emit(pos_ratio * self._duration)
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent):
        if self._is_dragging:
            pos_ratio = event.position().x() / self.width()
            pos_ratio = max(0.0, min(1.0, pos_ratio))
            self.setValue(int(pos_ratio * 1000))
            if self._duration > 0:
                self.seek_requested.emit(pos_ratio * self._duration)
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton:
            self._is_dragging = False
            pos_ratio = event.position().x() / self.width()
            pos_ratio = max(0.0, min(1.0, pos_ratio))
            if self._duration > 0:
                self.seek_requested.emit(pos_ratio * self._duration)
            event.accept()
        else:
            super().mouseReleaseEvent(event)
