"""
Small mouse-transparent widgets drawn over the video: the top scrim with the
file name, the thin progress line shown while the controls are hidden, and the
big pause / play symbol shown over the picture.
"""
from PySide6.QtWidgets import QWidget, QGraphicsOpacityEffect
from PySide6.QtCore import Qt, QRectF, QPointF, QSize, QEasingCurve, QTimer
from PySide6.QtGui import (
    QPainter, QLinearGradient, QColor, QFont, QFontMetrics, QPen, QPolygonF
)

from ui.glass_button import Tweening, glass_disc_pixmap, icon_swap_params
from ui.icons import get_svg_icon

PROGRESS_COLOR = QColor(255, 255, 255, 235)      # plain white, like the timeline fill


class _OverlayBase(QWidget):
    def __init__(self, parent):
        super().__init__(parent)
        # Clicks fall through to the video viewport (drag, double-click, menu).
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)


class TopScrim(_OverlayBase):
    """Dark gradient at the top edge: the shade behind the floating title bar, with the media title under it."""
    HEIGHT = 124
    TEXT_LEFT = 16

    def __init__(self, parent):
        super().__init__(parent)
        self._title = ""
        self._inset = 0              # height of the title bar above the file name (0 in fullscreen)
        self.setFixedHeight(self.HEIGHT)
        self._fx = QGraphicsOpacityEffect(self)
        self._fx.setOpacity(1.0)
        self.setGraphicsEffect(self._fx)

    def set_title(self, title: str):
        self._title = title
        self.update()

    def set_bar_inset(self, inset: int):
        if inset != self._inset:
            self._inset = inset
            self.update()

    def set_opacity(self, value: float):
        self._fx.setOpacity(max(0.0, min(1.0, value)))

    def paintEvent(self, event):
        p = QPainter(self)
        g = QLinearGradient(0, 0, 0, self.height())
        g.setColorAt(0.0, QColor(0, 0, 0, 176))
        g.setColorAt(0.5, QColor(0, 0, 0, 84))
        g.setColorAt(1.0, QColor(0, 0, 0, 0))
        p.fillRect(self.rect(), g)
        if self._title:
            font = QFont("Segoe UI Variable Text", 11)
            font.setWeight(QFont.DemiBold)
            p.setFont(font)
            text = QFontMetrics(font).elidedText(self._title, Qt.ElideRight, self.width() - 2 * self.TEXT_LEFT)
            base = self._inset + 22                 # just below the title bar
            p.setPen(QColor(0, 0, 0, 120))          # soft shadow
            p.drawText(self.TEXT_LEFT + 1, base + 1, text)
            p.setPen(QColor(255, 255, 255, 240))
            p.drawText(self.TEXT_LEFT, base, text)


class MiniProgress(_OverlayBase):
    """3px progress line at the bottom edge, visible while controls are hidden."""
    def __init__(self, parent):
        super().__init__(parent)
        self._ratio = 0.0
        self.setFixedHeight(3)

    def set_ratio(self, ratio: float):
        self._ratio = max(0.0, min(1.0, ratio))
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(255, 255, 255, 56))
        p.fillRect(0, 0, int(self.width() * self._ratio), self.height(), PROGRESS_COLOR)


class CenterBadge(_OverlayBase, Tweening):
    """Big pause / play symbol over the picture, on a DARK glass disc (the light glass of the controls
    would vanish on bright frames).

    Pausing shows the PAUSE symbol, resuming shows the PLAY symbol (swapping from the PAUSE symbol if that
    is still up); either stays for the same short moment (HOLD_MS) and then fades out. It fades and grows in, and the two symbols swap like the play
    button's (old one shrinks away, new one grows in). Nothing flashes when a file simply starts playing.
    """
    DISC = 88
    MARGIN = 14                 # room for the shadow
    ICON = 62
    SHOW_MS, HIDE_MS, SWAP_MS = 260, 220, 300
    HOLD_MS = 500               # how long the symbol (pause or play) stays before it fades out
    SCALE_FROM = 0.88           # the disc grows from this size while it fades in

    def __init__(self, parent):
        super().__init__(parent)
        side = self.DISC + 2 * self.MARGIN
        self.setFixedSize(side, side)
        self._vis = 0.0
        self._swap = 1.0
        self._hiding = False
        self._icons = {"pause": get_svg_icon("pause_glass", size=self.ICON, color="#F2FBFF"),
                       "play": get_svg_icon("play_glass", size=self.ICON, color="#F2FBFF")}
        self._mode = "pause"
        self._prev_mode = None
        self._armed = False         # ignores the pause that comes with loading a file, until it first plays
        self._paused = False        # the file was paused (so the next play is a resume worth showing)
        self._init_tweens()
        self._hold = QTimer(self)
        self._hold.setSingleShot(True)
        self._hold.setInterval(self.HOLD_MS)
        self._hold.timeout.connect(self._fade_out)

    # --- driven by the player state -----------------------------------------------------------
    def reset(self):
        """A new file is loading: hide at once and stay quiet until it has started playing."""
        self._armed = False
        self._paused = False
        self._hold.stop()
        self._hiding = False
        self._tweens.clear()
        self._timer.stop()
        self._vis = 0.0
        self._prev_mode = None
        self._swap = 1.0
        self._mode = "pause"
        QWidget.setVisible(self, False)

    @property
    def armed(self) -> bool:
        return self._armed

    def arm(self):
        """The file is really playing now: from here on a pause shows the symbol."""
        self._armed = True

    def set_playing(self, is_playing: bool, has_media: bool = True):
        if not has_media:
            self._hold.stop()
            self._fade_out()
            return
        if is_playing:
            self._armed = True
            resumed, self._paused = self._paused, False
            if resumed:                                     # a resume always shows PLAY, even if the PAUSE symbol is gone
                self._set_mode("play")
                self._fade_in()
                self._hold.start()
            return
        if not self._armed:
            return                                          # the pause that comes with loading a file
        self._paused = True
        self._set_mode("pause")
        self._fade_in()
        self._hold.start()                                  # the pause symbol fades out after the same moment

    def _set_mode(self, mode: str):
        if mode == self._mode:
            return
        if self.isVisible() and self._vis > 0.02:
            self._prev_mode = self._mode
            self._swap = 0.0
            self._animate("swap", 1.0, self.SWAP_MS, QEasingCurve.Linear)
        else:
            self._prev_mode = None
            self._swap = 1.0
        self._mode = mode

    def _fade_in(self):
        self._hiding = False
        if not self.isVisible():
            self._vis = 0.0
            QWidget.setVisible(self, True)
        self._animate("vis", 1.0, self.SHOW_MS)

    def _fade_out(self):
        if not self.isVisible():
            return
        if not self._hiding:
            self._hiding = True
            self._animate("vis", 0.0, self.HIDE_MS, QEasingCurve.InCubic)
            if "vis" not in self._tweens:
                self._finish_hide()

    def setVisible(self, visible: bool):
        """Plain show / hide (used when the window lays out); the state-driven path is set_playing."""
        if visible:
            self._fade_in()
        else:
            self._hold.stop()
            self._fade_out()

    def _finish_hide(self):
        self._hiding = False
        self._prev_mode = None
        QWidget.setVisible(self, False)

    def _tick(self):
        Tweening._tick(self)
        if self._hiding and "vis" not in self._tweens:
            self._finish_hide()

    def paintEvent(self, event):
        if self._vis <= 0.002:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setRenderHint(QPainter.SmoothPixmapTransform, True)
        dpr = self.devicePixelRatioF()
        p.setOpacity(self._vis)
        p.translate(self.width() / 2.0, self.height() / 2.0)
        sc = self.SCALE_FROM + (1.0 - self.SCALE_FROM) * self._vis
        p.scale(sc, sc)
        p.translate(-self.width() / 2.0, -self.height() / 2.0)
        p.drawPixmap(0, 0, glass_disc_pixmap(self.DISC, self.MARGIN, dpr, dark=True))
        px = self.ICON
        x, y = (self.width() - px) / 2.0, (self.height() - px) / 2.0

        def draw_icon(mode, opacity, scale):
            if opacity <= 0.002:
                return
            pm = self._icons[mode].pixmap(QSize(px, px), dpr)
            p.save()
            p.setOpacity(self._vis * opacity)
            p.translate(self.width() / 2.0, self.height() / 2.0)
            p.scale(scale, scale)
            p.drawPixmap(QPointF(-px / 2.0, -px / 2.0), pm)
            p.restore()

        if self._prev_mode is not None and self._swap < 1.0:
            old_o, old_s, new_o, new_s = icon_swap_params(self._swap)
            draw_icon(self._prev_mode, old_o, old_s)
            draw_icon(self._mode, new_o, new_s)
        else:
            draw_icon(self._mode, 1.0, 1.0)
