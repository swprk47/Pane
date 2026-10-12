"""
The control-bar editor (the "컨트롤 배치" tab of the settings panel): edit the bar the way it looks.

    ┌ 왼쪽 ─────┐ ┌ 가운데 ────────────────┐ ┌ 오른쪽 ─────────────────┐
    │ (시간)(배속) │ │ (이전)(-5초)(재생)(+5초)(다음) │ │ (캡처)(자막)(볼륨)(전체)(설정) │
    └───────────┘ └────────────────────────┘ └───────────────────────┘
     숨긴 버튼  [＋ 프레임-] [＋ 프레임+]

The bar is drawn as three dashed zones holding the real (glass) buttons. Drag a button to another place or
zone, drag it down to the "숨긴 버튼" row (or press its ✕) to hide it, and drag / click a hidden one to
bring it back. ``LayoutEditor`` is the widget; the panel around it is ``ui.settings_panel.SettingsPanel``.
"""
import math

from PySide6.QtCore import Qt, QPointF, QRectF, QSize, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QFontMetrics, QLinearGradient, QPainter, QPen
from PySide6.QtWidgets import QApplication, QWidget

from ui.glass_button import glass_disc_pixmap
from ui.icons import get_svg_icon

ZONES = ("left", "center", "right")
ZONE_TITLES = {"left": "왼쪽", "center": "가운데", "right": "오른쪽"}
ZONE_WEIGHTS = {"left": 1.0, "center": 2.2, "right": 2.2}
SHORT_NAMES = {
    "play_pause": "재생", "prev_file": "이전", "next_file": "다음", "prev_frame": "프레임-", "next_frame": "프레임+",
    "seek_backward": "-5초", "seek_forward": "+5초", "time_label": "시간", "speed_button": "배속",
    "screenshot": "캡처", "subtitle": "자막", "volume": "볼륨", "fullscreen": "전체", "settings": "설정",
}
FALLBACK_ICONS = {"time_label": "clock", "speed_button": "speed"}      # buttons that are text, not icons

ITEM_W, ITEM_H, DISC, ICON = 48, 64, 38, 18
BAR_PAD, ZONE_GAP, ZONE_PAD, ZONE_LABEL_H = 12, 10, 8, 24
HINT_H = 34
CHIP_H, CHIP_GAP, TRAY_PAD, TRAY_LABEL_W = 30, 8, 10, 74

DIALOG_MARGIN = 28           # transparent room around the panel for its shadow
DIALOG_CONTENT_W = 760


class LayoutEditor(QWidget):
    changed = Signal()

    def __init__(self, layout: dict, metadata: dict, default_layout: dict, parent=None):
        super().__init__(parent)
        self._meta = metadata
        self._default = default_layout
        self._zones = {z: [k for k in layout.get(z, []) if k in metadata] for z in ZONES}
        self._dedupe()
        self._geo_cache = None
        self._icons = {}
        self._hover = None            # ("x", key) | ("item", key) | ("chip", key)
        self._press = None            # (key, source, QPointF)
        self._drag = None             # dict(key, source, pos, target) while a button is being dragged
        self.setMouseTracking(True)
        self.setMinimumWidth(360)

    # --- the layout --------------------------------------------------------------------------
    def _dedupe(self):
        seen = set()
        for z in ZONES:
            kept = []
            for k in self._zones[z]:
                if k not in seen:
                    seen.add(k)
                    kept.append(k)
            self._zones[z] = kept

    def layout(self) -> dict:
        return {z: list(self._zones[z]) for z in ZONES}

    def set_layout(self, layout: dict):
        self._zones = {z: [k for k in layout.get(z, []) if k in self._meta] for z in ZONES}
        self._dedupe()
        self._cancel_drag()
        self._invalidate()
        self.changed.emit()

    def hidden_keys(self) -> list:
        placed = {k for z in ZONES for k in self._zones[z]}
        return [k for k in self._meta if k not in placed]

    def zone_of(self, key: str):
        for z in ZONES:
            if key in self._zones[z]:
                return z
        return None

    def default_zone(self, key: str) -> str:
        for z in ZONES:
            if key in self._default.get(z, []):
                return z
        return "right"

    def move_key(self, key: str, container: str, index: int = None):
        """Put ``key`` into a zone (at ``index``, default the end) or hide it (``container`` = "hidden")."""
        if key not in self._meta:
            return
        for z in ZONES:
            if key in self._zones[z]:
                self._zones[z].remove(key)
        if container in ZONES:
            lst = self._zones[container]
            lst.insert(len(lst) if index is None else max(0, min(index, len(lst))), key)
        self._invalidate()
        self.changed.emit()

    # --- geometry ----------------------------------------------------------------------------
    def _invalidate(self):
        self._geo_cache = None
        self._geo()                       # (the height follows the layout at once, not a paint later)
        self.update()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._geo_cache = None

    def _shown(self, zone: str) -> list:
        drag_key = self._drag["key"] if self._drag else None
        return [k for k in self._zones[zone] if k != drag_key]

    def _shown_hidden(self) -> list:
        drag_key = self._drag["key"] if self._drag else None
        return [k for k in self.hidden_keys() if k != drag_key]

    def _chip_width(self, key: str) -> int:
        f = self._chip_font()
        return 10 + 14 + 6 + QFontMetrics(f).horizontalAdvance(self._meta[key]["name"]) + 8 + 14 + 8

    def _chip_font(self) -> QFont:
        f = QFont(self.font())
        f.setPixelSize(11)
        f.setWeight(QFont.DemiBold)
        return f

    def _geo(self) -> dict:
        if self._geo_cache is not None:
            return self._geo_cache
        w = max(self.width(), 360)
        inner = w - 2 * BAR_PAD - 2 * ZONE_GAP
        total = sum(ZONE_WEIGHTS.values())
        zone_w = {z: inner * ZONE_WEIGHTS[z] / total for z in ZONES}
        keys = {z: self._shown(z) for z in ZONES}
        cap = {z: max(1, int((zone_w[z] - 2 * ZONE_PAD) // ITEM_W)) for z in ZONES}
        rows = {z: max(1, math.ceil(len(keys[z]) / cap[z])) for z in ZONES}
        # a zone that is the drag target keeps room for the key about to land in it
        if self._drag and self._drag.get("target") and self._drag["target"][0] == "zone":
            tz = self._drag["target"][1]
            rows[tz] = max(rows[tz], math.ceil((len(keys[tz]) + 1) / cap[tz]))
        n_rows = max(rows.values())
        zone_h = ZONE_LABEL_H + n_rows * ITEM_H + 6
        bar_h = zone_h + 2 * BAR_PAD

        zone_rects, item_rects, row_tops, caps = {}, {}, {}, cap
        x = BAR_PAD
        for z in ZONES:
            zr = QRectF(x, BAR_PAD, zone_w[z], zone_h)
            zone_rects[z] = zr
            row_tops[z] = zr.top() + ZONE_LABEL_H
            items = keys[z]
            for r in range(math.ceil(len(items) / cap[z]) if items else 0):
                chunk = items[r * cap[z]:(r + 1) * cap[z]]
                row_w = len(chunk) * ITEM_W
                if z == "left":
                    start = zr.left() + ZONE_PAD
                elif z == "center":
                    start = zr.center().x() - row_w / 2.0
                else:
                    start = zr.right() - ZONE_PAD - row_w
                for i, k in enumerate(chunk):
                    item_rects[k] = QRectF(start + i * ITEM_W, row_tops[z] + r * ITEM_H, ITEM_W, ITEM_H)
            x += zone_w[z] + ZONE_GAP

        # the hidden-buttons tray: chips flow left to right and wrap
        tray_top = bar_h + HINT_H
        chip_rects, cx, cy = {}, TRAY_PAD + TRAY_LABEL_W, tray_top + TRAY_PAD
        for k in self._shown_hidden():
            cw = self._chip_width(k)
            if cx + cw > w - TRAY_PAD and cx > TRAY_PAD + TRAY_LABEL_W:
                cx, cy = TRAY_PAD + TRAY_LABEL_W, cy + CHIP_H + CHIP_GAP
            chip_rects[k] = QRectF(cx, cy, cw, CHIP_H)
            cx += cw + CHIP_GAP
        tray_h = max(TRAY_PAD * 2 + CHIP_H, (cy + CHIP_H + TRAY_PAD) - tray_top)
        total_h = int(tray_top + tray_h)

        geo = {"w": w, "bar_h": bar_h, "zone_rects": zone_rects, "item_rects": item_rects, "row_tops": row_tops,
               "caps": caps, "keys": keys, "chip_rects": chip_rects, "tray": QRectF(0, tray_top, w, tray_h),
               "total_h": total_h}
        if self.height() != total_h:
            self.setFixedHeight(total_h)
            self.updateGeometry()
        self._geo_cache = geo
        return geo

    def fit(self):
        """Work out the height this layout needs (the dialog asks before the first paint)."""
        self._geo_cache = None
        self._geo()

    # --- for the tests and the hit tests ---------------------------------------------------------
    def item_rect(self, key: str) -> QRectF:
        g = self._geo()
        return g["item_rects"].get(key) or g["chip_rects"][key]

    def zone_rect(self, zone: str) -> QRectF:
        return self._geo()["zone_rects"][zone]

    def tray_rect(self) -> QRectF:
        return self._geo()["tray"]

    def _x_badge(self, key: str) -> QRectF:
        r = self._geo()["item_rects"][key]
        cx = r.center().x() + DISC / 2.0 - 2
        return QRectF(cx - 8, r.top() + 4 - 6, 16, 16)

    def _hit(self, pos: QPointF):
        g = self._geo()
        for k, r in g["item_rects"].items():
            if self._x_badge(k).contains(pos) and self._hover and self._hover[1] == k:
                return ("x", k)
        for k, r in g["item_rects"].items():
            if r.contains(pos):
                return ("item", k)
        for k, r in g["chip_rects"].items():
            if r.contains(pos):
                return ("chip", k)
        return None

    def _index_in_zone(self, zone: str, pos: QPointF) -> int:
        g = self._geo()
        items = g["keys"][zone]
        if not items:
            return 0
        cap, top = g["caps"][zone], g["row_tops"][zone]
        n_rows = math.ceil(len(items) / cap)
        row = max(0, min(n_rows - 1, int((pos.y() - top) // ITEM_H)))
        chunk = items[row * cap:(row + 1) * cap]
        before = sum(1 for k in chunk if g["item_rects"][k].center().x() < pos.x())
        return row * cap + before

    def _target_for(self, pos: QPointF):
        g = self._geo()
        if g["tray"].contains(pos):
            return ("hidden",)
        for z in ZONES:
            if g["zone_rects"][z].adjusted(-ZONE_GAP / 2, -6, ZONE_GAP / 2, 6).contains(pos):
                return ("zone", z, self._index_in_zone(z, pos))
        if pos.y() <= g["bar_h"] and pos.y() >= 0:
            nearest = min(ZONES, key=lambda z: abs(g["zone_rects"][z].center().x() - pos.x()))
            return ("zone", nearest, self._index_in_zone(nearest, pos))
        return None

    # --- mouse ---------------------------------------------------------------------------------
    def _cancel_drag(self):
        self._press, self._drag = None, None
        self.unsetCursor()

    def mousePressEvent(self, event):
        if event.button() != Qt.LeftButton:
            return super().mousePressEvent(event)
        hit = self._hit(event.position())
        if hit and hit[0] == "x":
            self.move_key(hit[1], "hidden")
            self._hover = None
        elif hit:
            self._press = (hit[1], hit[0], event.position())
        event.accept()

    def mouseMoveEvent(self, event):
        pos = event.position()
        if self._press and not self._drag:
            if (pos - self._press[2]).manhattanLength() >= QApplication.startDragDistance():
                self._drag = {"key": self._press[0], "source": self._press[1], "pos": pos, "target": None}
                self.setCursor(Qt.ClosedHandCursor)
                self._geo_cache = None
        if self._drag:
            self._drag["pos"] = pos
            target = self._target_for(pos)
            if target != self._drag["target"]:
                self._drag["target"] = target
                self._geo_cache = None
            self.update()
            return
        hit = self._hit(pos)
        hover = (hit[0], hit[1]) if hit else None
        if hover != self._hover:
            self._hover = hover
            self.setCursor(Qt.OpenHandCursor if hit and hit[0] != "x" else (Qt.PointingHandCursor if hit else Qt.ArrowCursor))
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() != Qt.LeftButton:
            return super().mouseReleaseEvent(event)
        if self._drag:
            key, target = self._drag["key"], self._drag["target"]
            self._cancel_drag()
            if target:
                if target[0] == "hidden":
                    self.move_key(key, "hidden")
                else:
                    self.move_key(key, target[1], target[2])
            else:
                self._invalidate()
        elif self._press:
            key, kind = self._press[0], self._press[1]
            self._press = None
            if kind == "chip":                                  # a click on a hidden button brings it back
                self.move_key(key, self.default_zone(key))
        event.accept()

    def leaveEvent(self, event):
        if self._hover:
            self._hover = None
            self.update()
        super().leaveEvent(event)

    # --- painting --------------------------------------------------------------------------------
    def _icon(self, key: str, size: int):
        ck = (key, size)
        if ck not in self._icons:
            name = self._meta[key].get("icon_name") or FALLBACK_ICONS.get(key)
            self._icons[ck] = get_svg_icon(name, size=size, color="#F2FBFF") if name else None
        return self._icons[ck]

    def _paint_button(self, p: QPainter, key: str, rect: QRectF, lifted: bool = False, x_badge: bool = False):
        dpr = self.devicePixelRatioF()
        disc = QRectF(rect.center().x() - DISC / 2.0, rect.top() + 4, DISC, DISC)
        p.drawPixmap(disc.topLeft(), glass_disc_pixmap(DISC, 0, dpr, shadow=False))
        icon = self._icon(key, ICON)
        if icon:
            p.drawPixmap(QPointF(disc.center().x() - ICON / 2.0, disc.center().y() - ICON / 2.0),
                         icon.pixmap(QSize(ICON, ICON), dpr))
        f = QFont(self.font())
        f.setPixelSize(10)
        p.setFont(f)
        p.setPen(QColor(255, 255, 255, 170))
        p.drawText(QRectF(rect.left() - 4, disc.bottom() + 4, rect.width() + 8, 14), Qt.AlignHCenter | Qt.AlignVCenter,
                   SHORT_NAMES.get(key, key))
        if x_badge:
            b = QRectF(disc.right() - 10, disc.top() - 6, 16, 16)
            p.setPen(QPen(QColor(255, 255, 255, 90), 1))
            p.setBrush(QColor(28, 30, 40, 245))
            p.drawEllipse(b)
            p.setPen(QPen(QColor(255, 255, 255, 235), 1.4, Qt.SolidLine, Qt.RoundCap))
            c = b.center()
            p.drawLine(QPointF(c.x() - 3, c.y() - 3), QPointF(c.x() + 3, c.y() + 3))
            p.drawLine(QPointF(c.x() + 3, c.y() - 3), QPointF(c.x() - 3, c.y() + 3))

    def paintEvent(self, event):
        g = self._geo()
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setRenderHint(QPainter.SmoothPixmapTransform, True)
        target = self._drag["target"] if self._drag else None

        bar = QRectF(0.5, 0.5, g["w"] - 1, g["bar_h"] - 1)
        grad = QLinearGradient(bar.topLeft(), bar.bottomLeft())
        grad.setColorAt(0.0, QColor(0, 0, 0, 46))
        grad.setColorAt(1.0, QColor(0, 0, 0, 150))
        p.setBrush(QBrush(grad))
        p.setPen(QPen(QColor(232, 240, 250, 42), 1))
        p.drawRoundedRect(bar, 22, 22)

        label_font = QFont(self.font())
        label_font.setPixelSize(11)
        label_font.setWeight(QFont.DemiBold)
        for z in ZONES:
            zr = g["zone_rects"][z]
            lit = bool(target and target[0] == "zone" and target[1] == z)
            pen = QPen(QColor(255, 255, 255, 190 if lit else 76), 1.4 if lit else 1)
            if not lit:
                pen.setStyle(Qt.DashLine)
            p.setPen(pen)
            p.setBrush(QColor(255, 255, 255, 16) if lit else Qt.NoBrush)
            p.drawRoundedRect(zr, 14, 14)
            p.setFont(label_font)
            p.setPen(QColor(255, 255, 255, 128))
            p.drawText(QRectF(zr.left() + 10, zr.top() + 4, zr.width() - 20, 16), Qt.AlignLeft | Qt.AlignVCenter,
                       f"{ZONE_TITLES[z]}")

        for k, r in g["item_rects"].items():
            hovered = bool(self._hover and self._hover[1] == k and not self._drag)
            self._paint_button(p, k, r, x_badge=hovered)

        # where the dragged button would land
        if target and target[0] == "zone":
            z, idx = target[1], target[2]
            items, cap = g["keys"][z], g["caps"][z]
            zr = g["zone_rects"][z]
            if items and idx < len(items):
                ir = g["item_rects"][items[idx]]
                x, y = ir.left(), ir.top()
            elif items:
                ir = g["item_rects"][items[-1]]
                x, y = ir.right(), ir.top()
            else:
                x, y = zr.center().x(), zr.top() + ZONE_LABEL_H
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(255, 255, 255, 235))
            p.drawRoundedRect(QRectF(x - 1.5, y + 6, 3, DISC - 4), 1.5, 1.5)

        # the tray of hidden buttons
        tray = g["tray"].adjusted(0.5, 0.5, -0.5, -0.5)
        lit_tray = bool(target and target[0] == "hidden")
        pen = QPen(QColor(255, 255, 255, 190 if lit_tray else 66), 1.4 if lit_tray else 1)
        pen.setStyle(Qt.SolidLine if lit_tray else Qt.DashLine)
        p.setPen(pen)
        p.setBrush(QColor(255, 255, 255, 14) if lit_tray else Qt.NoBrush)
        p.drawRoundedRect(tray, 16, 16)
        p.setFont(label_font)
        p.setPen(QColor(255, 255, 255, 150))
        first_h = CHIP_H
        p.drawText(QRectF(TRAY_PAD + 4, tray.top() + TRAY_PAD, TRAY_LABEL_W, first_h), Qt.AlignLeft | Qt.AlignVCenter, "숨긴 버튼")
        chip_font = self._chip_font()
        for k, r in g["chip_rects"].items():
            hovered = bool(self._hover and self._hover[0] == "chip" and self._hover[1] == k and not self._drag)
            p.setPen(QPen(QColor(232, 240, 250, 150 if hovered else 90), 1, Qt.DashLine))
            p.setBrush(QColor(255, 255, 255, 30 if hovered else 10))
            p.drawRoundedRect(r, CHIP_H / 2, CHIP_H / 2)
            icon = self._icon(k, 14)
            dpr = self.devicePixelRatioF()
            if icon:
                p.drawPixmap(QPointF(r.left() + 10, r.center().y() - 7), icon.pixmap(QSize(14, 14), dpr))
            p.setFont(chip_font)
            p.setPen(QColor(255, 255, 255, 215))
            p.drawText(QRectF(r.left() + 30, r.top(), r.width() - 54, r.height()), Qt.AlignLeft | Qt.AlignVCenter,
                       self._meta[k]["name"])
            p.setPen(QColor(255, 255, 255, 170))
            p.drawText(QRectF(r.right() - 24, r.top(), 18, r.height()), Qt.AlignCenter, "＋")

        p.setFont(label_font)
        p.setPen(QColor(255, 255, 255, 100))
        p.drawText(QRectF(0, g["bar_h"] + 4, g["w"], HINT_H - 8), Qt.AlignCenter,
                   "아이콘을 끌어서 옮기세요. 아래 \"숨긴 버튼\"으로 끌어 내리거나 ✕를 누르면 숨겨져요.")

        if self._drag:
            d = self._drag
            pos = d["pos"]
            ghost = QRectF(pos.x() - ITEM_W / 2.0, pos.y() - 4 - DISC / 2.0, ITEM_W, ITEM_H)
            p.setOpacity(0.9)
            self._paint_button(p, d["key"], ghost)
            p.setOpacity(1.0)
