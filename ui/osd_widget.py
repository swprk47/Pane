from PySide6.QtWidgets import QWidget, QLabel, QHBoxLayout, QGraphicsOpacityEffect
from PySide6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve

class GlassOSDWidget(QWidget):
    """
    Apple Glass-styled pill-shaped On-Screen Display (OSD) badge.
    Displays speed, volume, seek feedback, and fades out smoothly.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setFixedHeight(48)
        self.setMinimumWidth(120)

        self._init_ui()

        # Opacity animation for smooth fade-in and fade-out
        self.opacity_effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self.opacity_effect)
        self.opacity_effect.setOpacity(0.0)

        self.fade_anim = QPropertyAnimation(self.opacity_effect, b"opacity")
        self.fade_anim.setEasingCurve(QEasingCurve.OutCubic)

        # Timer to hold visible state before fading out
        self.hold_timer = QTimer(self)
        self.hold_timer.setSingleShot(True)
        self.hold_timer.timeout.connect(self._start_fade_out)

        self.hide()

    def _init_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(18, 6, 18, 6)
        layout.setSpacing(8)

        self.icon_label = QLabel("", self)
        self.icon_label.setStyleSheet("font-size: 16px; color: #0A84FF;")
        layout.addWidget(self.icon_label)

        self.text_label = QLabel("", self)
        self.text_label.setObjectName("GlassOSD")
        self.text_label.setAlignment(Qt.AlignCenter)
        self.text_label.setStyleSheet("""
            QLabel#GlassOSD {
                font-size: 15px;
                font-weight: 600;
                color: #FFFFFF;
                background-color: transparent;
                border: none;
            }
        """)
        layout.addWidget(self.text_label)

        self.setStyleSheet("""
            GlassOSDWidget {
                background-color: rgba(22, 22, 30, 0.88);
                border: 1px solid rgba(255, 255, 255, 0.22);
                border-radius: 20px;
            }
        """)

    def show_message(self, text: str, icon: str = ""):
        """Show OSD badge with text and optional icon, then fade out."""
        self.text_label.setText(text)
        if icon:
            self.icon_label.setText(icon)
            self.icon_label.show()
        else:
            self.icon_label.hide()

        self.adjustSize()

        # Reposition to top-center of parent if parent exists
        if self.parent():
            parent_w = self.parent().width()
            my_w = self.width()
            self.move(int((parent_w - my_w) / 2), 60)

        self.show()
        self.raise_()

        # Instant or fast fade-in
        self.fade_anim.stop()
        self.opacity_effect.setOpacity(1.0)

        # Hold for 1000ms then fade out
        self.hold_timer.stop()
        self.hold_timer.start(1000)

    def _start_fade_out(self):
        self.fade_anim.stop()
        self.fade_anim.setDuration(400)
        self.fade_anim.setStartValue(1.0)
        self.fade_anim.setEndValue(0.0)
        self.fade_anim.finished.connect(self._on_fade_finished)
        self.fade_anim.start()

    def _on_fade_finished(self):
        if self.opacity_effect.opacity() == 0.0:
            self.hide()
