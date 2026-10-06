"""
The glass look of Pane's controls, and buttons that animate instead of snapping between states.

    kind="disc"   clear glass disc (transport buttons): nearly transparent body, a soft frosted band just
                  inside a thin light rim, a thin shade inside the top-left edge, a soft drop shadow.
    kind="pill"   the same glass as a rounded pill that carries text (speed button, presets, badges).
    kind="plain"  no glass at rest, a soft round highlight fades in on hover / press.
    kind="flat"   like plain but a rounded square (title bar buttons); ``danger`` turns the highlight red.

Hover and press only change BRIGHTNESS (the glass never shrinks). Every state change fades, and a changing
icon swaps by shrinking the old one away and growing the new one in. The static glass is painted once into a
cached pixmap; only the brightness overlay, the icon and the text are painted per frame.
``paint_glass_panel`` draws the same material for floating panels. Design: PROGRESS.md ("글라스 ...").
"""
import time

from PySide6.QtCore import Qt, QEasingCurve, QPointF, QRectF, QSize, QTimer
from PySide6.QtGui import (QBrush, QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen,
                           QPixmap, QRadialGradient)
from PySide6.QtWidgets import QPushButton

# --- motion (one place to tune the feel) --------------------------------------------------------
HOVER_MS = 180          # highlight fades in / out
PRESS_IN_MS = 70        # brightens almost immediately on press
PRESS_OUT_MS = 320      # and settles back slowly
ICON_FADE_MS = 300      # play <-> pause swap (old icon shrinks away, new one grows in)
ICON_SWAP_SCALE = 0.78  # how small the icons get at the far end of the swap
ACTIVE_MS = 220         # a pill turning "on" (selected preset, PIP active)

# --- glass material (design "R2": clear glass, white -> pale serenity rim) -----------------------
DISC_MARGIN = 10        # transparent room around a disc for the shadow
BODY_TOP = (214, 210, 244, 28)       # body fill, top-left  (alpha 0..255)
BODY_BOTTOM = (190, 200, 235, 18)    # body fill, bottom-right
RIM_STOPS = ((0.00, (255, 255, 255, 242)), (0.35, (222, 234, 246, 204)),
             (0.62, (150, 178, 208, 179)), (1.00, (190, 222, 238, 242)))
FROST_ALPHA = 0.30      # frosted band inside the rim
SHADE = (60, 70, 115, 51)            # thin shade inside the top-left edge
SHADOW = (25, 35, 65)
HOVER_FILL, PRESS_FILL = 0.085, 0.18      # extra white fill (fraction of 255) at full hover / press
HOVER_FROST, PRESS_FROST = 0.06, 0.14     # extra frost at full hover / press
PLAIN_HOVER, PLAIN_PRESS = 0.14, 0.26     # highlight alpha of the plain / flat buttons
ACTIVE_FILL = 0.24                        # extra fill of an active pill
ACTIVE_RIM = (255, 255, 255)              # rim laid over an active pill (white, like the rest of the glass)
ACTIVE_RIM_TINT = (179, 206, 229)         # serenity: only for pills created with tint=True (the PIP badge)
DANGER = (232, 17, 35)                    # close button highlight
TEXT_COLOR = QColor(255, 255, 255, 235)
ACCENT_TEXT = QColor(208, 225, 239)

# panels (speed / volume popups): dark enough to read over any video, same rim and frost
PANEL_FILL = (22, 24, 33, 218)
PANEL_FROST_ALPHA = 0.16

_base_cache = {}
_panel_cache = {}


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


def _shape(rect: QRectF, kind: str, radius: float) -> QPainterPath:
    path = QPainterPath()
    if kind == "disc":
        path.addEllipse(rect)
    else:
        path.addRoundedRect(rect, radius, radius)
    return path


def _rim_brush(rect: QRectF) -> QBrush:
    g = QLinearGradient(rect.topLeft(), rect.bottomRight())
    for pos, col in RIM_STOPS:
        g.setColorAt(pos, _c(col))
    return QBrush(g)


def _frost_band(p: QPainter, rect: QRectF, kind: str, radius: float, band: float, alpha: float):
    """Soft white band just inside the edge, fading toward the middle."""
    if alpha <= 0:
        return
    if kind == "disc":
        r = rect.width() / 2.0
        g = QRadialGradient(rect.center(), r)
        g.setColorAt(max(0.0, (r - band) / r), QColor(255, 255, 255, 0))
        g.setColorAt(1.0, QColor(255, 255, 255, int(255 * alpha)))
        p.fillPath(_shape(rect, kind, radius), QBrush(g))
        return
    steps = max(3, int(band))
    p.setBrush(Qt.NoBrush)
    for i in range(steps):
        a = alpha * (1.0 - i / steps) ** 2
        p.setPen(QPen(QColor(255, 255, 255, int(255 * a)), 1.0))
        inset = i + 0.5
        r = max(0.0, radius - inset)
        p.drawRoundedRect(rect.adjusted(inset, inset, -inset, -inset), r, r)


def _build_base(kind: str, w: int, h: int, margin: int, radius: float, shadow: bool, dpr: float) -> QPixmap:
    """Shadow + body + frost + shade + rim of a resting glass shape."""
    tw, th = w + 2 * margin, h + 2 * margin
    pm = QPixmap(int(tw * dpr), int(th * dpr))
    pm.setDevicePixelRatio(dpr)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing, True)
    rect = QRectF(margin, margin, w, h)
    path = _shape(rect, kind, radius)
    short = min(w, h)

    if shadow and margin > 0:
        # soft drop shadow, only OUTSIDE the shape (the glass stays see-through)
        outside = QPainterPath()
        outside.addRect(QRectF(0, 0, tw, th))
        outside = outside.subtracted(path)
        p.save()
        p.setClipPath(outside)
        p.setPen(Qt.NoPen)
        dx, dy = short * 0.07, short * 0.16
        layers = 9
        for i in range(layers):
            grow = i * (margin * 0.55 / layers)
            r2 = rect.translated(dx, dy).adjusted(-grow, -grow, grow, grow)
            p.setBrush(QColor(*SHADOW, int(10 + 8 * (layers - i) / layers)))
            if kind == "disc":
                p.drawEllipse(r2)
            else:
                rr = r2.height() / 2.0 if kind == "pill" else radius + grow
                p.drawRoundedRect(r2, rr, rr)
        p.restore()

    p.save()
    p.setClipPath(path)
    bg = QLinearGradient(rect.topLeft(), rect.bottomRight())
    bg.setColorAt(0.0, _c(BODY_TOP))
    bg.setColorAt(1.0, _c(BODY_BOTTOM))
    p.fillPath(path, QBrush(bg))
    _frost_band(p, rect, kind, radius, min(13.0, short * 0.36), FROST_ALPHA)
    shifted = _shape(rect.translated(1.5, 1.5), kind, radius)
    p.fillPath(path.subtracted(shifted), _c(SHADE))
    p.restore()

    rim_w = 2.0 if short >= 60 else 1.5
    p.setPen(QPen(_rim_brush(rect), rim_w))
    p.setBrush(Qt.NoBrush)
    inner = rect.adjusted(rim_w / 2, rim_w / 2, -rim_w / 2, -rim_w / 2)
    if kind == "disc":
        p.drawEllipse(inner)
    else:
        rr = max(0.0, radius - rim_w / 2)
        p.drawRoundedRect(inner, rr, rr)
    p.end()
    return pm


def paint_glass_panel(p: QPainter, rect: QRectF, radius: float):
    """The glass material as a floating panel: dark clear body, frosted edge, thin light rim."""
    dpr = p.device().devicePixelRatioF() if hasattr(p.device(), "devicePixelRatioF") else 1.0
    key = (int(rect.width()), int(rect.height()), radius, dpr)
    pm = _panel_cache.get(key)
    if pm is None:
        w, h = int(rect.width()), int(rect.height())
        pm = QPixmap(int(w * dpr), int(h * dpr))
        pm.setDevicePixelRatio(dpr)
        pm.fill(Qt.transparent)
        q = QPainter(pm)
        q.setRenderHint(QPainter.Antialiasing, True)
        r = QRectF(0, 0, w, h)
        path = _shape(r, "panel", radius)
        q.save()
        q.setClipPath(path)
        q.fillPath(path, _c(PANEL_FILL))
        bg = QLinearGradient(r.topLeft(), r.bottomRight())
        bg.setColorAt(0.0, _c(BODY_TOP, 1.3))
        bg.setColorAt(1.0, _c(BODY_BOTTOM, 1.0))
        q.fillPath(path, QBrush(bg))
        _frost_band(q, r, "panel", radius, 12.0, PANEL_FROST_ALPHA)
        q.fillPath(path.subtracted(_shape(r.translated(1.5, 1.5), "panel", radius)), _c(SHADE, 0.7))
        q.restore()
        q.setPen(QPen(_rim_brush(r), 1.5))
        q.setBrush(Qt.NoBrush)
        q.drawRoundedRect(r.adjusted(0.75, 0.75, -0.75, -0.75), radius - 0.75, radius - 0.75)
        q.end()
        _panel_cache[key] = pm
    p.drawPixmap(rect.topLeft(), pm)


class Tweening:
    """Mixin: named float values (``self._hover`` ...) that ease toward a target on a 16 ms timer.

    The host provides ``update()`` and ``isVisible()``; hidden widgets jump straight to the target.
    """

    def _init_tweens(self):
        self._tweens = {}
        self._timer = QTimer(self)
        self._timer.setInterval(16)
        self._timer.timeout.connect(self._tick)

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

    def _stop_tweens(self):
        self._tweens.clear()
        self._timer.stop()


class GlassButton(QPushButton, Tweening):
    def __init__(self, parent=None, kind: str = "plain", diameter: int = 40, icon_px: int = 16, *,
                 width: int = None, text_px: int = 13, text_pad: int = 14, shadow: bool = None,
                 radius: float = None, danger: bool = False, accent_text: bool = False, base=None, tint: bool = False, bold: bool = False):
        super().__init__(parent)
        self.kind = kind
        self._d = diameter                       # disc diameter, or the height of a pill / flat button
        self._explicit_w = width
        self._text_pad = text_pad
        self._accent_text = accent_text
        self._tint = tint                        # serenity rim when active (the speed / PIP pills are the only ones)
        self._danger = danger
        self._base = base                        # resting fill (r, g, b, a) of a plain / flat button
        if shadow is None:
            shadow = kind == "disc"
        self._shadow = shadow
        self._m = DISC_MARGIN if (shadow and kind == "disc") else (6 if (shadow and kind == "pill") else 0)
        self._radius = radius if radius is not None else (diameter / 2.0 if kind in ("disc", "pill") else 8.0)
        self._font_px = text_px
        self._bold = bold
        self.setObjectName("GlassButton")
        self.setIconSize(QSize(icon_px, icon_px))
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.NoFocus)
        self._hover = 0.0
        self._press = 0.0
        self._fade = 1.0                 # icon cross-fade progress (1 = settled)
        self._act = 0.0                  # active (selected) pill
        self._active = False
        self._prev_icon = None
        self._init_tweens()
        if kind == "pill":
            f = QFont(self.font())
            f.setPixelSize(text_px)
            f.setWeight(QFont.Bold if bold else QFont.DemiBold)
            self.setFont(f)
        self._apply_size()

    # --- size ---------------------------------------------------------------------------------
    def _content_width(self) -> int:
        if self._explicit_w is not None:
            return self._explicit_w
        if self.kind == "pill":
            return max(self._d, self.fontMetrics().horizontalAdvance(self.text()) + 2 * self._text_pad)
        return self._d

    def _apply_size(self):
        w, h = self._content_width() + 2 * self._m, self._d + 2 * self._m
        # (QSS min/max sizes beat setFixedSize, so state the exact size here too)
        font_qss = ""
        if self.kind == "pill":                     # state the font here too: no outer QSS rule may override it
            weight = 700 if self._bold else 600
            font_qss = f"font-size:{self._font_px}px;font-weight:{weight};"
        self.setStyleSheet("QPushButton#GlassButton{background:transparent;border:none;padding:0;" + font_qss +
                           f"min-width:{w}px;max-width:{w}px;min-height:{h}px;max-height:{h}px;}}")
        self.setFixedSize(w, h)

    def setText(self, text):
        super().setText(text)
        if hasattr(self, "_font_px"):
            self._apply_size()
        self.update()

    # --- state --------------------------------------------------------------------------------
    def setActive(self, active: bool):
        """A selected / switched-on pill: brighter glass and a serenity rim."""
        self._active = bool(active)
        self._animate("act", 1.0 if active else 0.0, ACTIVE_MS)

    def isActive(self) -> bool:
        return self._active

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
        self._stop_tweens()
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

    def _glass_rect(self) -> QRectF:
        return QRectF(self._m, self._m, self.width() - 2 * self._m, self.height() - 2 * self._m)

    def _paint_glass(self, p, rect, h, pr):
        dpr = self.devicePixelRatioF()
        key = (self.kind, int(rect.width()), int(rect.height()), self._m, self._radius, self._shadow, dpr)
        base = _base_cache.get(key)
        if base is None:
            base = _base_cache[key] = _build_base(self.kind, int(rect.width()), int(rect.height()), self._m,
                                                   self._radius, self._shadow, dpr)
        p.drawPixmap(0, 0, base)
        path = _shape(rect, self.kind, self._radius)
        fill = HOVER_FILL * h + PRESS_FILL * pr + ACTIVE_FILL * self._act
        if fill > 0:
            p.fillPath(path, QColor(255, 255, 255, int(255 * fill)))
        frost = HOVER_FROST * h + PRESS_FROST * pr
        if frost > 0:
            p.save()
            p.setClipPath(path)
            _frost_band(p, rect, self.kind, self._radius, min(13.0, min(rect.width(), rect.height()) * 0.36), frost)
            p.restore()
        if self._act > 0:
            p.setPen(QPen(QColor(*(ACTIVE_RIM_TINT if self._tint else ACTIVE_RIM), int(235 * self._act)), 1.8))
            p.setBrush(Qt.NoBrush)
            inner = rect.adjusted(1, 1, -1, -1)
            if self.kind == "disc":
                p.drawEllipse(inner)
            else:
                r = max(0.0, self._radius - 1)
                p.drawRoundedRect(inner, r, r)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setRenderHint(QPainter.SmoothPixmapTransform, True)
        h, pr = self._hover, self._press
        rect = self._glass_rect()
        if self.kind in ("disc", "pill"):
            self._paint_glass(p, rect, h, pr)
        else:
            if self._danger:
                a = min(1.0, 0.95 * h + 0.25 * pr)
                col = QColor(*DANGER, int(255 * a))
            else:
                col = QColor(255, 255, 255, int(255 * (PLAIN_HOVER * h + PLAIN_PRESS * pr)))
            p.setPen(Qt.NoPen)
            inner = rect.adjusted(1, 1, -1, -1)
            for fill in ([QColor(*self._base)] if self._base else []) + ([col] if col.alpha() > 0 else []):
                p.setBrush(fill)
                if self.kind == "plain":
                    p.drawEllipse(inner)
                else:
                    p.drawRoundedRect(inner, self._radius, self._radius)
        if self.text():
            color = ACCENT_TEXT if self._accent_text else TEXT_COLOR
            if self._act > 0:
                color = QColor(255, 255, 255, 255)
            p.setPen(color)
            p.setFont(self.font())
            p.drawText(rect, Qt.AlignCenter, self.text())
        if self._prev_icon is not None and self._fade < 1.0:
            old_o, old_s, new_o, new_s = icon_swap_params(self._fade)
            self._draw_icon(p, self._prev_icon, old_o, old_s)
            self._draw_icon(p, self.icon(), new_o, new_s)
        else:
            self._draw_icon(p, self.icon(), 1.0)
