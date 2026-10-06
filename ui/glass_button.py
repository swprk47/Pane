"""
Round overlay buttons that animate instead of snapping between states.

    kind="disc"   a clear glass disc (the transport buttons): nearly transparent body, a soft frosted
                  band just inside a thin light rim, a thin shade inside the top-left edge, a soft
                  drop shadow. Hover and press only change BRIGHTNESS (the disc never shrinks).
    kind="plain"  no disc at rest, a soft round highlight fades in on hover / press.

Both fade between hover / press states and cross-fade the icon when it changes (play <-> pause).
The static glass is painted once into a cached pixmap; only the brightness overlay and the icon are
painted per frame. Design: see PROGRESS.md ("글라스 재생 버튼").
"""
import time

from PySide6.QtCore import Qt, QEasingCurve, QPointF, QRectF, QSize, QTimer
from PySide6.QtGui import (QBrush, QColor, QLinearGradient, QPainter, QPainterPath, QPen,
                           QPixmap, QRadialGradient)
from PySide6.QtWidgets import QPushButton

# --- motion (one place to tune the feel) --------------------------------------------------------
HOVER_MS = 180          # highlight fades in / out
PRESS_IN_MS = 70        # brightens almost immediately on press
PRESS_OUT_MS = 320      # and settles back slowly
ICON_FADE_MS = 300      # play <-> pause swap (old icon shrinks away, new one grows in)
ICON_SWAP_SCALE = 0.78  # how small the icons get at the far end of the swap

# --- glass material (design "R2": clear glass, white -> pale serenity rim) -----------------------
DISC_MARGIN = 10        # transparent room around the disc for the shadow
BODY_TOP = (214, 210, 244, 28)       # body fill, top-left  (alpha 0..255)
BODY_BOTTOM = (190, 200, 235, 18)    # body fill, bottom-right
RIM_STOPS = ((0.00, (255, 255, 255, 242)), (0.35, (222, 234, 246, 204)),
             (0.62, (150, 178, 208, 179)), (1.00, (190, 222, 238, 242)))
FROST_ALPHA = 0.30      # frosted band inside the rim
SHADE = (60, 70, 115, 51)            # thin shade inside the top-left edge
SHADOW = (25, 35, 65)
HOVER_FILL, PRESS_FILL = 0.085, 0.18      # extra white fill (fraction of 255) at full hover / press
HOVER_FROST, PRESS_FROST = 0.06, 0.14     # extra frost at full hover / press
PLAIN_HOVER, PLAIN_PRESS = 0.14, 0.26     # highlight alpha of the plain buttons

_base_cache = {}


def _smooth(x: float, a: float, b: float) -> float:
    """0 before a, 1 after b, smooth in between."""
    if x <= a:
        return 0.0
    if x >= b:
        return 1.0
    t = (x - a) / (b - a)
    return t * t * (3 - 2 * t)


def icon_swap_params(t: float):
    """(old_opacity, old_scale, new_opacity, new_scale) for swap progress t in 0..1.

    The old icon fades out and shrinks first, the new one starts a little later and grows in, so the two
    different shapes (triangle <-> bars) are never both half-transparent on top of each other for long.
    """
    k = 1.0 - ICON_SWAP_SCALE
    old_o = 1.0 - _smooth(t, 0.0, 0.55)
    new_o = _smooth(t, 0.30, 1.0)
    old_s = 1.0 - k * _smooth(t, 0.0, 0.7)
    new_s = ICON_SWAP_SCALE + k * _smooth(t, 0.25, 1.0)
    return old_o, old_s, new_o, new_s


def _c(rgba, scale=1.0):
    r, g, b, a = rgba
    return QColor(r, g, b, max(0, min(255, int(a * scale))))


def _disc_path(rect: QRectF) -> QPainterPath:
    path = QPainterPath()
    path.addEllipse(rect)
    return path


def _build_base(diameter: int, margin: int, dpr: float) -> QPixmap:
    """Shadow + body + frost + shade + rim of a resting glass disc."""
    size = diameter + 2 * margin
    pm = QPixmap(int(size * dpr), int(size * dpr))
    pm.setDevicePixelRatio(dpr)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing, True)
    disc = QRectF(margin, margin, diameter, diameter)
    r = diameter / 2.0
    c = disc.center()
    disc_path = _disc_path(disc)

    # soft drop shadow, only OUTSIDE the disc (the glass stays see-through)
    outside = QPainterPath()
    outside.addRect(QRectF(0, 0, size, size))
    outside = outside.subtracted(disc_path)
    p.save()
    p.setClipPath(outside)
    sc = QPointF(c.x() + r * 0.09, c.y() + r * 0.20)
    g = QRadialGradient(sc, r * 1.12)
    g.setColorAt(0.0, QColor(*SHADOW, 72))
    g.setColorAt(0.70, QColor(*SHADOW, 58))
    g.setColorAt(1.0, QColor(*SHADOW, 0))
    p.setPen(Qt.NoPen)
    p.setBrush(QBrush(g))
    p.drawEllipse(sc, r * 1.12, r * 1.12)
    p.restore()

    p.save()
    p.setClipPath(disc_path)
    # body: flat, almost clear
    bg = QLinearGradient(disc.topLeft(), disc.bottomRight())
    bg.setColorAt(0.0, _c(BODY_TOP))
    bg.setColorAt(1.0, _c(BODY_BOTTOM))
    p.fillPath(disc_path, QBrush(bg))
    # frosted band just inside the rim, fading toward the middle
    band = min(13.0, r * 0.36)
    fg = QRadialGradient(c, r)
    fg.setColorAt(max(0.0, (r - band) / r), QColor(255, 255, 255, 0))
    fg.setColorAt(1.0, QColor(255, 255, 255, int(255 * FROST_ALPHA)))
    p.fillPath(disc_path, QBrush(fg))
    # thin shade inside the top-left edge (the rim looks slightly recessed)
    shifted = _disc_path(disc.translated(1.5, 1.5))
    p.fillPath(disc_path.subtracted(shifted), _c(SHADE))
    p.restore()

    # light rim
    w = 2.0 if diameter >= 60 else 1.5
    rg = QLinearGradient(disc.topLeft(), disc.bottomRight())
    for pos, col in RIM_STOPS:
        rg.setColorAt(pos, _c(col))
    pen = QPen(QBrush(rg), w)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    p.drawEllipse(disc.adjusted(w / 2, w / 2, -w / 2, -w / 2))
    p.end()
    return pm


class GlassButton(QPushButton):
    def __init__(self, parent=None, kind: str = "plain", diameter: int = 40, icon_px: int = 16):
        super().__init__(parent)
        self.kind = kind
        self._d = diameter
        self._m = DISC_MARGIN if kind == "disc" else 0
        size = diameter + 2 * self._m
        self.setObjectName("GlassButton")
        # the controller's QSS gives every QPushButton min/max sizes: opt out
        # (QSS min/max sizes beat setFixedSize, so state the exact size here too)
        self.setStyleSheet(f"QPushButton#GlassButton{{background:transparent;border:none;padding:0;"
                           f"min-width:{size}px;max-width:{size}px;min-height:{size}px;max-height:{size}px;}}")
        self.setFixedSize(size, size)
        self.setIconSize(QSize(icon_px, icon_px))
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.NoFocus)
        self._hover = 0.0
        self._press = 0.0
        self._fade = 1.0                 # icon cross-fade progress (1 = settled)
        self._prev_icon = None
        self._tweens = {}
        self._timer = QTimer(self)
        self._timer.setInterval(16)
        self._timer.timeout.connect(self._tick)

    # --- state animation ----------------------------------------------------------------------
    # One shared 60 Hz timer drives every value (hover, press, icon swap) of this button.
    def _animate(self, name, target, ms, curve=QEasingCurve.OutCubic):
        current = getattr(self, "_" + name)
        if not self.isVisible() or ms <= 0 or abs(current - target) < 1e-3:
            self._tweens.pop(name, None)
            setattr(self, "_" + name, target)
            self.update()
            return
        self._tweens[name] = (float(current), float(target), time.perf_counter(), ms / 1000.0, QEasingCurve(curve))
        if not self._timer.isActive():
            self._timer.start()

    def _tick(self):
        now = time.perf_counter()
        for name in list(self._tweens):
            start, end, t0, dur, curve = self._tweens[name]
            x = min(1.0, (now - t0) / dur)
            setattr(self, "_" + name, start + (end - start) * curve.valueForProgress(x))
            if x >= 1.0:
                setattr(self, "_" + name, end)
                del self._tweens[name]
        if not self._tweens:
            self._timer.stop()
        self.update()

    def enterEvent(self, event):
        self._animate("hover", 1.0, HOVER_MS)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._animate("hover", 0.0, HOVER_MS)
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        super().mousePressEvent(event)
        if self.isDown():
            self._animate("press", 1.0, PRESS_IN_MS)

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        self._animate("press", 0.0, PRESS_OUT_MS)

    def hideEvent(self, event):
        self._tweens.clear()
        self._timer.stop()
        self._hover = self._press = 0.0
        self._fade = 1.0
        self._prev_icon = None
        super().hideEvent(event)

    # --- icon cross-fade ----------------------------------------------------------------------
    def setIcon(self, icon):
        old = self.icon()
        super().setIcon(icon)
        if (self.isVisible() and not old.isNull() and not icon.isNull()
                and old.cacheKey() != icon.cacheKey()):
            self._prev_icon = old
            self._fade = 0.0
            self._animate("fade", 1.0, ICON_FADE_MS, QEasingCurve.Linear)
        else:
            self.update()

    # --- painting -----------------------------------------------------------------------------
    def _draw_icon(self, p, icon, opacity, scale=1.0):
        if icon is None or icon.isNull() or opacity <= 0:
            return
        dpr = self.devicePixelRatioF()
        px = self.iconSize().width()
        pm = icon.pixmap(QSize(px, px), dpr)
        p.save()
        p.setOpacity(opacity)
        p.translate(self.width() / 2.0, self.height() / 2.0)
        p.scale(scale, scale)
        p.drawPixmap(QPointF(-px / 2.0, -px / 2.0), pm)
        p.restore()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setRenderHint(QPainter.SmoothPixmapTransform, True)
        h, pr = self._hover, self._press
        if self.kind == "disc":
            dpr = self.devicePixelRatioF()
            key = (self._d, self._m, dpr)
            base = _base_cache.get(key)
            if base is None:
                base = _base_cache[key] = _build_base(self._d, self._m, dpr)
            p.drawPixmap(0, 0, base)
            disc = QRectF(self._m, self._m, self._d, self._d)
            r = self._d / 2.0
            path = _disc_path(disc)
            fill = HOVER_FILL * h + PRESS_FILL * pr
            if fill > 0:
                p.fillPath(path, QColor(255, 255, 255, int(255 * fill)))
            frost = HOVER_FROST * h + PRESS_FROST * pr
            if frost > 0:
                band = min(13.0, r * 0.36)
                g = QRadialGradient(disc.center(), r)
                g.setColorAt(max(0.0, (r - band) / r), QColor(255, 255, 255, 0))
                g.setColorAt(1.0, QColor(255, 255, 255, int(255 * frost)))
                p.fillPath(path, QBrush(g))
        else:
            a = PLAIN_HOVER * h + PLAIN_PRESS * pr
            if a > 0:
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(255, 255, 255, int(255 * a)))
                p.drawEllipse(QRectF(self.rect()).adjusted(1, 1, -1, -1))
        if self._prev_icon is not None and self._fade < 1.0:
            old_o, old_s, new_o, new_s = icon_swap_params(self._fade)
            self._draw_icon(p, self._prev_icon, old_o, old_s)
            self._draw_icon(p, self.icon(), new_o, new_s)
        else:
            self._draw_icon(p, self.icon(), 1.0)
