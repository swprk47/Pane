"""The on/off switch used in the glass panels (the subtitle switch of the track panel, the settings panel's rows)."""
from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QWidget


class GlassSwitch(QWidget):
    toggled = Signal(bool)

    def __init__(self, checked=True, parent=None):
        super().__init__(parent)
        self.checked = checked
        self.setFixedSize(34, 20)
        self.setCursor(Qt.PointingHandCursor)

    def setChecked(self, checked: bool):
        """Set it without announcing (the caller already knows)."""
        self.checked = bool(checked)
        self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self.isEnabled() and self.rect().contains(event.position().toPoint()):
            self.checked = not self.checked
            self.update()
            self.toggled.emit(self.checked)
            event.accept()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        dim = 1.0 if self.isEnabled() else 0.45
        p.setOpacity(dim)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(255, 255, 255, 217) if self.checked else QColor(255, 255, 255, 46))
        p.drawRoundedRect(QRectF(0, 0, 34, 20), 10, 10)
        p.setBrush(QColor(20, 24, 30) if self.checked else QColor(255, 255, 255, 115))
        p.drawEllipse(QRectF(16, 2, 16, 16) if self.checked else QRectF(2, 2, 16, 16))
