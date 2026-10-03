from PySide6.QtWidgets import QFrame, QVBoxLayout, QSlider, QLabel
from PySide6.QtCore import Qt, Signal, QTimer


class VolumePopup(QFrame):
    """
    Vertical glass volume slider that floats above the mute button while the
    mouse hovers over it. Stays open while the mouse is on the button or on
    the popup itself, then closes after a short grace period.
    """
    value_changed = Signal(int)

    def __init__(self, parent):
        super().__init__(parent)
        self.setObjectName("VolumePopup")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setFixedSize(50, 168)
        self.hide()

        self.setStyleSheet("""
            QFrame#VolumePopup {
                background-color: rgba(26, 27, 36, 0.94);
                border: 1px solid rgba(255, 255, 255, 0.24);
                border-radius: 25px;
            }
            QLabel {
                color: rgba(255, 255, 255, 0.85);
                font-size: 11px;
                font-weight: 600;
                background: transparent;
            }
            QSlider::groove:vertical {
                width: 8px;
                background: rgba(255, 255, 255, 0.18);
                border-radius: 4px;
            }
            QSlider::sub-page:vertical {
                background: rgba(255, 255, 255, 0.18);
                border-radius: 4px;
            }
            QSlider::add-page:vertical {
                background: #0A84FF;
                border-radius: 4px;
            }
            QSlider::handle:vertical {
                background: rgba(255, 255, 255, 0.55);
                border: 1px solid rgba(255, 255, 255, 0.85);
                height: 14px;
                margin-left: -7px;
                margin-right: -7px;
                border-radius: 7px;
            }
            QSlider::handle:vertical:hover {
                background: rgba(255, 255, 255, 0.85);
            }
        """)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 14, 0, 10)
        lay.setSpacing(8)

        self.slider = QSlider(Qt.Vertical, self)
        self.slider.setRange(0, 100)
        self.slider.setValue(100)
        self.slider.setCursor(Qt.PointingHandCursor)
        self.slider.valueChanged.connect(self._on_value)
        lay.addWidget(self.slider, 1, Qt.AlignHCenter)

        self.label = QLabel("100", self)
        self.label.setAlignment(Qt.AlignCenter)
        lay.addWidget(self.label)

        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.setInterval(280)
        self._hide_timer.timeout.connect(self.hide)

    def _on_value(self, v: int):
        self.label.setText(str(v))
        self.value_changed.emit(v)

    def set_value(self, v: int):
        self.slider.blockSignals(True)
        self.slider.setValue(int(v))
        self.slider.blockSignals(False)
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
