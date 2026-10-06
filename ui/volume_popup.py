from PySide6.QtWidgets import QFrame, QVBoxLayout, QLabel
from PySide6.QtCore import Qt, Signal, QTimer, QRectF
from PySide6.QtGui import QPainter

from ui.glass_button import paint_glass_panel
from ui.glass_slider import GlassSlider


class VolumePopup(QFrame):
    """
    Vertical glass volume slider that floats above the mute button while the
    mouse hovers over it. Stays open while the mouse is on the button or on
    the popup itself, then closes after a short grace period.
    """
    value_changed = Signal(int)
    RADIUS = 19

    def __init__(self, parent):
        super().__init__(parent)
        self.setObjectName("VolumePopup")
        self.setFixedSize(38, 144)
        self.hide()

        # the glass panel is painted in paintEvent; only the label needs a style
        self.setStyleSheet("""
            QLabel {
                color: rgba(255, 255, 255, 0.85);
                font-size: 11px;
                font-weight: 600;
                background: transparent;
            }
        """)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 12, 0, 9)
        lay.setSpacing(6)

        self.slider = GlassSlider(Qt.Vertical, self)
        self.slider.setRange(0, 100)
        self.slider.setValue(100)
        self.slider.setFixedWidth(28)          # comfortable hit area around the thin track
        self.slider.valueChanged.connect(self._on_value)
        lay.addWidget(self.slider, 1, Qt.AlignHCenter)

        self.label = QLabel("100", self)
        self.label.setAlignment(Qt.AlignCenter)
        lay.addWidget(self.label)

        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.setInterval(280)
        self._hide_timer.timeout.connect(self.hide)

    def paintEvent(self, event):
        p = QPainter(self)
        paint_glass_panel(p, QRectF(self.rect()), self.RADIUS)

    def _on_value(self, v: int):
        self.label.setText(str(v))
        self.value_changed.emit(v)

    def set_value(self, v: int):
        self.slider.blockSignals(True)
        self.slider.setValue(int(v))
        self.slider.blockSignals(False)
        self.slider.update()
        self.label.setText(str(int(v)))

    def open_above(self, anchor):
        """Show centered above `anchor` (any descendant widget of our parent)."""
        self._hide_timer.stop()
        pos = anchor.mapTo(self.parentWidget(), anchor.rect().topLeft())
        x = pos.x() + (anchor.width() - self.width()) // 2
        y = pos.y() - self.height() - 4
        self.move(max(4, x), max(4, y))
        self.show()
        self.raise_()

    def schedule_close(self):
        self._hide_timer.start()

    def enterEvent(self, event):
        self._hide_timer.stop()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hide_timer.start()
        super().leaveEvent(event)
