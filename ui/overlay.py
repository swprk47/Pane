"""
Small mouse-transparent widgets drawn over the video: the top scrim with the
file name, the thin progress line shown while the controls are hidden, and the
big pause / play symbol shown over the picture.
"""
from PySide6.QtWidgets import QWidget, QGraphicsOpacityEffect
from PySide6.QtCore import Qt, QPointF, QRectF, QSize, QEasingCurve, QTimer
from PySide6.QtGui import (
    QPainter, QLinearGradient, QColor, QFont, QFontMetrics, QPainterPath, QPen
)

from core.thumbnails import thumbnail_box
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
            # Already invisible: still mark it hidden for real, else the window's first show() brings it up
            # (the pause symbol used to appear over the empty start screen).
            QWidget.setVisible(self, False)
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


class SeekIndicator(_OverlayBase, Tweening):
    """Shown at the left / right edge of the picture when the video jumps by time (arrow keys, the +-5 s buttons):
    a dark shade that fades in from the screen edge, with a chevron arrow and the seconds on it ("5s"). The arrow
    starts as a single chevron and the second one slides out from behind it (played again on every press).

    Pressing again in the same direction adds up ("5초" -> "10초" -> "15초"); the other direction starts again on
    its own side. It stays HOLD_MS after the last press, then fades out and hides itself, so it costs nothing while idle
    (only while it is on screen, every frame is composited over the video like the other overlays).
    """
    WIDTH_RATIO = 0.34
    HOLD_MS = 700
    SHOW_MS, HIDE_MS, ARROW_MS = 140, 320, 280
    INSET = 36                  # icon distance from the screen edge
    ICON = 34
    GAP = 10
    SHADE_EDGE, SHADE_MID = 0.72, 0.38      # darkness at the screen edge and 55% of the way in (then 0)

    def __init__(self, parent):
        super().__init__(parent)
        self.side = "right"
        self.total = 0
        self._area = None
        self._vis = 0.0
        self._hiding = False
        self._arrow = 1.0           # 0: one chevron, 1: both (the second one slides out and fades in)
        self._init_tweens()
        self._hold = QTimer(self)
        self._hold.setSingleShot(True)
        self._hold.setInterval(self.HOLD_MS)
        self._hold.timeout.connect(self._fade_out)
        QWidget.setVisible(self, False)

    @property
    def text(self) -> str:
        return f"{self.total:g}s"

    # --- driven by the seeks ------------------------------------------------------------------
    def show_seek(self, delta: float):
        side = "right" if delta > 0 else "left"
        if side == self.side and self._hold.isActive():
            self.total += abs(delta)
        else:
            self.total = abs(delta)
        self.side = side
        self.place(self._area or self.parentWidget().rect())
        self._hiding = False
        if not self.isVisible():
            self._vis = 0.0
            QWidget.setVisible(self, True)
        self._animate("vis", 1.0, self.SHOW_MS)
        self._arrow = 0.0                                   # (every press plays the arrow again)
        self._tweens.pop("arrow", None)
        self._animate("arrow", 1.0, self.ARROW_MS)
        self._hold.start()
        self.update()

    def reset(self):
        """A new file is loading: gone at once."""
        self._hold.stop()
        self._hiding = False
        self._stop_tweens()
        self._vis = 0.0
        self.total = 0
        QWidget.setVisible(self, False)

    def place(self, area):
        """Cover the outer WIDTH_RATIO of `area` (the picture's rectangle) on the side it points to."""
        self._area = area
        w = round(area.width() * self.WIDTH_RATIO)
        x = area.right() + 1 - w if self.side == "right" else area.x()
        self.setGeometry(x, area.y(), w, area.height())

    def _fade_out(self):
        if not self.isVisible():
            return
        self._hiding = True
        self._animate("vis", 0.0, self.HIDE_MS, QEasingCurve.InCubic)
        if "vis" not in self._tweens:
            self._finish_hide()

    def _finish_hide(self):
        self._hiding = False
        self.total = 0
        QWidget.setVisible(self, False)

    def _tick(self):
        Tweening._tick(self)
        if self._hiding and "vis" not in self._tweens:
            self._finish_hide()

    # --- painting -----------------------------------------------------------------------------
    def paintEvent(self, event):
        if self._vis <= 0.002:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setRenderHint(QPainter.SmoothPixmapTransform, True)
        w, h = self.width(), self.height()
        right = self.side == "right"
        p.setOpacity(self._vis)

        grad = QLinearGradient(w if right else 0, 0, 0 if right else w, 0)      # starts at the screen edge
        grad.setColorAt(0.0, QColor(0, 0, 0, round(255 * self.SHADE_EDGE)))
        grad.setColorAt(0.55, QColor(0, 0, 0, round(255 * self.SHADE_MID)))
        grad.setColorAt(1.0, QColor(0, 0, 0, 0))
        p.fillRect(self.rect(), grad)

        font = QFont("Segoe UI Variable Text")
        font.setFamilies(["Segoe UI Variable Text", "Segoe UI"])
        font.setPixelSize(17)
        font.setWeight(QFont.DemiBold)
        p.setFont(font)
        p.setPen(QColor(255, 255, 255))
        tw = QFontMetrics(font).horizontalAdvance(self.text)
        cy = h / 2.0
        if right:
            ix = w - self.INSET - self.ICON
            tx = ix - self.GAP - tw
        else:
            ix = self.INSET
            tx = ix + self.ICON + self.GAP
        self._draw_arrow(p, ix, cy - self.ICON / 2.0, right)
        p.drawText(QPointF(tx, cy + QFontMetrics(font).ascent() / 2.0 - 2), self.text)

    def _draw_arrow(self, p: QPainter, x: float, y: float, right: bool):
        """Two chevrons on the 24-unit grid of the control icons. The leading one (on the side the arrow points to) is
        always there; the other starts on top of it, invisible, and slides back to its own place as it fades in."""
        k = self.ICON / 24.0
        t = self._arrow
        d = 1 if right else -1
        lead_start = 13.0 if right else 11.0                # (the chevron starts at this x and its tip is 5 further)
        trail_start = (6.0 + (1.0 - t) * 7.0) if right else (18.0 - (1.0 - t) * 7.0)
        pen = QPen(QColor(255, 255, 255), 2.0 * k)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        base = p.opacity()
        for start, opacity in ((lead_start, 1.0), (trail_start, t)):
            if opacity <= 0.002:
                continue
            p.setOpacity(base * opacity)
            path = QPainterPath()
            path.moveTo(x + start * k, y + 17 * k)
            path.lineTo(x + (start + 5 * d) * k, y + 12 * k)
            path.lineTo(x + start * k, y + 7 * k)
            p.drawPath(path)
        p.setOpacity(base)


class SeekTimeTip(_OverlayBase):
    """The time under the mouse while it is over the seek bar (or while the handle is dragged): a small dark glass
    pill just above the bar, centred on the pointer and kept inside the picture. Hidden when not in use."""
    HEIGHT = 30
    PAD = 14
    EDGE = 8
    DOT = 8                  # a bookmark's amber dot before the text
    DOT_GAP = 8
    DETAIL_GAP = 8           # before the lighter text after it (the time of a bookmark or a chapter)

    def __init__(self, parent):
        super().__init__(parent)
        self.text = ""
        self.dot = None
        self.detail = ""
        font = QFont("Segoe UI Variable Text")
        font.setFamilies(["Segoe UI Variable Text", "Segoe UI"])
        font.setPixelSize(14)
        font.setWeight(QFont.DemiBold)
        self._font = font
        detail_font = QFont(font)
        detail_font.setWeight(QFont.Normal)
        self._detail_font = detail_font
        QWidget.setVisible(self, False)

    def show_at(self, text: str, x_center: float, y_bottom: float, bounds, dot=None, detail: str = ""):
        """Show `text` with the pill's bottom edge at y_bottom, centred on x_center, inside `bounds` (a QRect). `dot` (a
        QColor) puts a dot before the text, `detail` a lighter text after it; with neither it is the plain pill."""
        self.text, self.dot, self.detail = text, dot, detail
        w = QFontMetrics(self._font).horizontalAdvance(text) + 2 * self.PAD
        if dot is not None:
            w += self.DOT + self.DOT_GAP
        if detail:
            w += self.DETAIL_GAP + QFontMetrics(self._detail_font).horizontalAdvance(detail)
        self.resize(w, self.HEIGHT)
        x = round(x_center - w / 2.0)
        x = max(bounds.left() + self.EDGE, min(x, bounds.right() - self.EDGE - w + 1))
        self.move(x, round(y_bottom) - self.HEIGHT)
        if not self.isVisible():
            QWidget.setVisible(self, True)
            self.raise_()
        self.update()

    def hide_tip(self):
        QWidget.setVisible(self, False)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        p.setPen(QPen(QColor(255, 255, 255, 77), 1))
        p.setBrush(QColor(14, 14, 18, 168))
        p.drawRoundedRect(r, r.height() / 2, r.height() / 2)
        if self.dot is None and not self.detail:
            p.setFont(self._font)
            p.setPen(QColor(255, 255, 255))
            p.drawText(self.rect(), Qt.AlignCenter, self.text)
            return
        x = float(self.PAD)
        if self.dot is not None:
            p.setPen(Qt.NoPen)
            p.setBrush(self.dot)
            p.drawEllipse(QRectF(x, (self.height() - self.DOT) / 2.0, self.DOT, self.DOT))
            x += self.DOT + self.DOT_GAP
        p.setFont(self._font)
        p.setPen(QColor(255, 255, 255))
        text_w = QFontMetrics(self._font).horizontalAdvance(self.text)
        p.drawText(QRectF(x, 0, text_w + 2, self.height()), Qt.AlignLeft | Qt.AlignVCenter, self.text)
        if self.detail:
            p.setFont(self._detail_font)
            p.setPen(QColor(255, 255, 255, 180))
            p.drawText(QRectF(x + text_w + self.DETAIL_GAP, 0, self.width(), self.height()),
                       Qt.AlignLeft | Qt.AlignVCenter, self.detail)


class ThumbnailTip(_OverlayBase):
    """The picture of the moment under the pointer, just above the time pill (`SeekTimeTip`): 10 px rounded corners and
    the pill's light border. Its box follows the picture's aspect ratio (see core.thumbnails.thumbnail_box); a picture
    that does not fill it is fitted inside on dark bars, never stretched. Hidden when not in use."""
    GAP = 6                  # between this picture and the time pill below it
    EDGE = 8
    RADIUS = 10

    def __init__(self, parent):
        super().__init__(parent)
        self._image = None
        QWidget.setVisible(self, False)

    def show_at(self, image, x_center: float, y_bottom: float, bounds):
        """Show `image` with its bottom edge at y_bottom, centred on x_center, inside `bounds` (a QRect)."""
        self._image = image
        w, h = thumbnail_box(image.width() / image.height() if image.height() else 0)
        self.resize(w, h)
        x = round(x_center - w / 2.0)
        x = max(bounds.left() + self.EDGE, min(x, bounds.right() - self.EDGE - w + 1))
        self.move(x, round(y_bottom) - h)
        if not self.isVisible():
            QWidget.setVisible(self, True)
            self.raise_()
        self.update()

    def hide_tip(self):
        QWidget.setVisible(self, False)

    def paintEvent(self, event):
        if self._image is None:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setRenderHint(QPainter.SmoothPixmapTransform, True)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        clip = QPainterPath()
        clip.addRoundedRect(r, self.RADIUS, self.RADIUS)
        p.setClipPath(clip)
        p.fillRect(self.rect(), QColor(14, 14, 18))
        size = self._image.size().scaled(self.size(), Qt.KeepAspectRatio)
        target = QRectF((self.width() - size.width()) / 2.0, (self.height() - size.height()) / 2.0,
                        size.width(), size.height())
        p.drawImage(target, self._image)
        p.setClipping(False)
        p.setPen(QPen(QColor(255, 255, 255, 102), 1))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(r, self.RADIUS, self.RADIUS)
