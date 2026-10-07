"""
The card that appears when a video ends and another one follows in the folder:

    다음 영상 · 5초 뒤 재생
    lecture3.mp4                          [취소] (▶|)

A ring around the "play now" button counts the time down. Playing on its own, the button or Esc / "취소"
(stay on this video) are the three ways it ends. Resting the mouse on the card holds the countdown (the ring
dims); it goes on from where it stopped once the mouse leaves. It is a glass panel like the other popups.
"""
import time

from PySide6.QtCore import Qt, QEasingCurve, QRectF, QTimer, Signal
from PySide6.QtGui import QColor, QCursor, QFont, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import QWidget

from ui.glass_button import GlassButton, Tweening, paint_glass_panel
from ui.icons import get_svg_icon

NEXT_UP_SECONDS = 5.0
FADE_IN_MS = 220
HOLD_FADE_MS = 160       # the ring dims / brightens when the countdown is held / goes on
HOLD_DIM = 0.55          # how much of the ring's brightness a held countdown loses


class NextUpCard(QWidget, Tweening):
    play_now = Signal()
    cancelled = Signal()
    finished = Signal()          # the countdown ran out

    WIDTH, HEIGHT = 320, 112
    PAD = 18
    RING = 52                    # outer box of the ring around the play button
    RING_WIDTH = 3.0
    DISC = 38

    def __init__(self, parent):
        super().__init__(parent)
        self.setFixedSize(self.WIDTH, self.HEIGHT)
        self._name = ""
        self._seconds = NEXT_UP_SECONDS
        self._left = NEXT_UP_SECONDS
        self._last = 0.0
        self._vis = 0.0
        self._hold = 0.0
        self._held = False
        self._init_tweens()

        self._ring_box = QRectF(self.WIDTH - self.PAD - self.RING + 4, self.HEIGHT - 8 - self.RING, self.RING, self.RING)
        cx, cy = self._ring_box.center().x(), self._ring_box.center().y()

        self.btn_play = GlassButton(self, "disc", self.DISC, 22, shadow=False, calm=True)
        self.btn_play.setIcon(get_svg_icon("next_frame_glass", size=22, color="#F2FBFF"))
        self.btn_play.setToolTip("기다리지 않고 바로 재생")
        self.btn_play.move(round(cx - self.btn_play.width() / 2), round(cy - self.btn_play.height() / 2))
        self.btn_cancel = GlassButton(self, "pill", 30, text_px=12, text_pad=14, calm=True)
        self.btn_cancel.setText("취소")
        self.btn_cancel.setToolTip("이 영상에 머물기 (Esc)")
        self.btn_cancel.move(round(self._ring_box.left() - 10 - self.btn_cancel.width()), round(cy - self.btn_cancel.height() / 2))
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
        self._left = self._seconds
        self._last = time.perf_counter()
        self._vis = 0.0
        self._hold = 0.0
        self._held = False
        self._count.start()
        self.show()
        self.raise_()
        self._animate("vis", 1.0, FADE_IN_MS, QEasingCurve.OutCubic)
        self.update()

    def is_counting(self) -> bool:
        return self._count.isActive()

    def is_held(self) -> bool:
        """True while the mouse rests on the card and the countdown stands still."""
        return self._count.isActive() and self._held

    def remaining(self) -> float:
        if not self._count.isActive():
            return 0.0
        return max(0.0, self._left)

    def cancel(self):
        """Stay on the current video (also called when the user does something else)."""
        if self._count.isActive():
            self._end()
            self.cancelled.emit()
        else:
            self.hide()

    # --- internals ----------------------------------------------------------------------------
    def _mouse_over(self) -> bool:
        return self.rect().contains(self.mapFromGlobal(QCursor.pos()))

    def _end(self):
        self._count.stop()
        self._stop_tweens()
        self._held = False
        self.hide()

    def _on_play_now(self):
        if self._count.isActive():
            self._end()
            self.play_now.emit()

    def _on_count(self):
        now = time.perf_counter()
        dt, self._last = now - self._last, now
        held = self._mouse_over()
        if held != self._held:
            self._held = held
            self._animate("hold", 1.0 if held else 0.0, HOLD_FADE_MS)
        if not held:
            self._left -= dt
        if self._left <= 0.0:
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
        paint_glass_panel(p, QRectF(self.rect()), 18, calm=True)

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
        p.drawText(QRectF(self.PAD, self.PAD + 14, self.WIDTH - 2 * self.PAD, 22), Qt.AlignLeft | Qt.AlignVCenter, text)

        # the countdown ring around the play button: the lit arc shrinks clockwise from the top
        frac = left / self._seconds if self._seconds else 0.0
        ring = self._ring_box.adjusted(self.RING_WIDTH, self.RING_WIDTH, -self.RING_WIDTH, -self.RING_WIDTH)
        dim = 1.0 - HOLD_DIM * self._hold
        pen = QPen(QColor(255, 255, 255, 51), self.RING_WIDTH)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(ring)
        pen = QPen(QColor(255, 255, 255, int(240 * dim)), self.RING_WIDTH)
        pen.setCapStyle(Qt.RoundCap)
        p.setPen(pen)
        p.drawArc(ring, 90 * 16, -int(round(360 * 16 * frac)))
