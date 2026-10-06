"""
The card that appears when a video ends and another one follows in the folder:

    다음 영상 · 3초 뒤 재생
    lecture3.mp4                          [취소] [지금 재생]
    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

A thin line counts the time down. Playing on its own, "지금 재생" or Esc / "취소" (stay on this video) are the
three ways it ends. It is a glass panel like the other popups.
"""
import time

from PySide6.QtCore import Qt, QEasingCurve, QRectF, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter
from PySide6.QtWidgets import QWidget

from ui.glass_button import GlassButton, Tweening, paint_glass_panel

NEXT_UP_SECONDS = 3.0
FADE_IN_MS = 220


class NextUpCard(QWidget, Tweening):
    play_now = Signal()
    cancelled = Signal()
    finished = Signal()          # the countdown ran out

    WIDTH, HEIGHT = 380, 128
    PAD = 18

    def __init__(self, parent):
        super().__init__(parent)
        self.setFixedSize(self.WIDTH, self.HEIGHT)
        self._name = ""
        self._seconds = NEXT_UP_SECONDS
        self._started = 0.0
        self._vis = 0.0
        self._init_tweens()

        self.btn_play = GlassButton(self, "pill", 30, text_px=12, text_pad=14, bold=True)
        self.btn_play.setText("지금 재생")
        self.btn_play.setToolTip("기다리지 않고 바로 재생")
        self.btn_cancel = GlassButton(self, "pill", 30, text_px=12, text_pad=14)
        self.btn_cancel.setText("취소")
        self.btn_cancel.setToolTip("이 영상에 머물기 (Esc)")
        by = self.HEIGHT - self.PAD - 6 - self.btn_play.height()
        self.btn_play.move(self.WIDTH - self.PAD - self.btn_play.width(), by)
        self.btn_cancel.move(self.btn_play.x() - 8 - self.btn_cancel.width(), by)
        self.btn_play.clicked.connect(self._on_play_now)
        self.btn_cancel.clicked.connect(self.cancel)

        self._count = QTimer(self)
        self._count.setInterval(40)
        self._count.timeout.connect(self._on_count)
        self.hide()

    # --- API ----------------------------------------------------------------------------------
    def start(self, name: str, seconds: float = NEXT_UP_SECONDS):
        self._name = name
        self._seconds = max(0.05, float(seconds))
        self._started = time.perf_counter()
        self._vis = 0.0
        self._count.start()
        self.show()
        self.raise_()
        self._animate("vis", 1.0, FADE_IN_MS, QEasingCurve.OutCubic)
        self.update()

    def is_counting(self) -> bool:
        return self._count.isActive()

    def remaining(self) -> float:
        if not self._count.isActive():
            return 0.0
        return max(0.0, self._seconds - (time.perf_counter() - self._started))

    def cancel(self):
        """Stay on the current video (also called when the user does something else)."""
        if self._count.isActive():
            self._end()
            self.cancelled.emit()
        else:
            self.hide()

    # --- internals ----------------------------------------------------------------------------
    def _end(self):
        self._count.stop()
        self._stop_tweens()
        self.hide()

    def _on_play_now(self):
        if self._count.isActive():
            self._end()
            self.play_now.emit()

    def _on_count(self):
        if self.remaining() <= 0.0:
            self._end()
            self.finished.emit()
        else:
            self.update()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.cancel()
            event.accept()
        else:
            super().keyPressEvent(event)

    def paintEvent(self, event):
        if self._vis <= 0.002:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setOpacity(self._vis)
        paint_glass_panel(p, QRectF(self.rect()), 18)

        left = self.remaining()
        secs = max(1, int(left + 0.999))
        label_font = QFont(self.font())
        label_font.setPixelSize(11)
        label_font.setWeight(QFont.DemiBold)
        p.setFont(label_font)
        p.setPen(QColor(255, 255, 255, 150))
        p.drawText(QRectF(self.PAD, self.PAD - 2, self.WIDTH - 2 * self.PAD, 16), Qt.AlignLeft | Qt.AlignVCenter,
                   f"다음 영상 · {secs}초 뒤 재생")

        name_font = QFont(self.font())
        name_font.setPixelSize(15)
        name_font.setWeight(QFont.Bold)
        p.setFont(name_font)
        p.setPen(QColor(255, 255, 255, 240))
        text = QFontMetrics(name_font).elidedText(self._name, Qt.ElideMiddle, self.WIDTH - 2 * self.PAD)
        p.drawText(QRectF(self.PAD, self.PAD + 16, self.WIDTH - 2 * self.PAD, 24), Qt.AlignLeft | Qt.AlignVCenter, text)

        # the countdown line along the bottom edge of the card
        frac = left / self._seconds if self._seconds else 0.0
        track = QRectF(self.PAD, self.HEIGHT - 12, self.WIDTH - 2 * self.PAD, 3)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(255, 255, 255, 56))
        p.drawRoundedRect(track, 1.5, 1.5)
        p.setBrush(QColor(255, 255, 255, 235))
        p.drawRoundedRect(QRectF(track.x(), track.y(), track.width() * frac, track.height()), 1.5, 1.5)
