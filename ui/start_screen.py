"""
The start screen: what the window shows until a video is loaded.

    (logo, big)
    PANE
    영상을 이곳에 끌어다 놓으세요

    ╭────────────────────────────────────────────────────────╮
    │ [ 영상 열기 ]  │  이어보기                 00:07 / 00:10  (▷) │
    │                   Big_Buck_Bunny.mp4 ━━━━━━━━━━          │
    ╰────────────────────────────────────────────────────────╯

When a file could not be opened the hint line gives way to a notice in the warning colour (what happened, why,
and a "진단 정보 복사" link); it stays until the next file is opened.

A glass dock at the bottom (the same scrim glass as the panels) holds the open button and, when there is
one, the last video to go on with (name, a thin progress line, the time, a play button). Everything is
painted here; the screen lets drags and the right-click menu fall through to the video viewport under it
(drag = move the window). A plain click on the empty screen does nothing: opening a file is the button's job.
"""
import os

from PySide6.QtCore import Qt, QRect, QRectF, QPointF, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QFontMetrics, QLinearGradient, QPainter, QPainterPath, QPen, QRadialGradient
from PySide6.QtWidgets import QPushButton, QWidget

from ui.glass_button import GlassButton, paint_glass_panel
from core.version import APP_VERSION
from ui.icons import get_logo_pixmap, get_svg_icon, get_svg_pixmap

DOCK_H = 68
DOCK_BOTTOM = 38
DOCK_PAD = 12
DOCK_SIDE = 100              # room left / right of the dock in a wide window
DOCK_MIN_W, DOCK_MAX_W = 360, 720
OPEN_W, OPEN_H = 124, 44
GO_D = 44
TOP_SAFE = 44                # the window buttons live in the top corner
RESUME_MIN_SECONDS = 5.0     # the same threshold the player uses before it jumps back to a saved position

BG_CENTER, BG_MID, BG_EDGE = QColor("#12161D"), QColor("#05070A"), QColor("#000000")
VERSION_TEXT = f"v{APP_VERSION}"
WARN = QColor(240, 161, 75)                    # the warning colour (as in the info panel)
WARN_TEXT = QColor(245, 196, 138)
NOTICE_MAX_W, NOTICE_PAD, NOTICE_ICON = 440, 16, 20
HINT = "영상을 이곳에 끌어다 놓으세요"
HINT_DROP = "여기에 놓으면 바로 재생합니다"


def format_time(secs: float) -> str:
    s = int(max(0, secs))
    m, s = divmod(s, 60)
    h, m = divmod(m, 60)
    return f"{h:02d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


class _OpenButton(GlassButton):
    """The glass "영상 열기" pill: a folder icon, then the text."""
    ICON = 16

    def __init__(self, parent):
        super().__init__(parent, "pill", OPEN_H, width=OPEN_W, text_px=13, text_pad=20 + self.ICON + 9,
                         bold=True, align_left=True)
        self.setText("영상 열기")
        self.setToolTip("영상 파일 열기")
        self._folder = get_svg_pixmap("folder", self.ICON, "#F2FBFF", stroke_width=1.8)

    def paintEvent(self, event):
        super().paintEvent(event)
        p = QPainter(self)
        p.setRenderHint(QPainter.SmoothPixmapTransform, True)
        p.drawPixmap(QPointF(20, (self.height() - self.ICON) / 2.0), self._folder)


class _LinkButton(QPushButton):
    """A small underlined text button (the notice's "진단 정보 복사")."""

    def __init__(self, text: str, parent):
        super().__init__(text, parent)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.NoFocus)
        self.setFlat(True)
        f = QFont(self.font())
        f.setPixelSize(12)
        f.setUnderline(True)
        self.setFont(f)
        self.setFixedSize(QFontMetrics(f).horizontalAdvance(text) + 4, 20)
        self._hover = False

    def enterEvent(self, event):
        self._hover = True
        self.update()

    def leaveEvent(self, event):
        self._hover = False
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setFont(self.font())
        p.setPen(QColor(255, 255, 255, 230 if self._hover else 140))
        p.drawText(self.rect(), Qt.AlignLeft | Qt.AlignVCenter, self.text())


class StartScreen(QWidget):
    open_requested = Signal()
    resume_requested = Signal(str)
    copy_requested = Signal()          # the notice's "진단 정보 복사" link

    def __init__(self, parent):
        super().__init__(parent)
        self.setMouseTracking(True)
        self._logo = get_logo_pixmap(130)
        self._dragging = False
        self._resume = None            # dict: path, name, position, duration, label
        self._problem = None           # (title, hint) of the file that could not be opened

        # (created first so the dock's other buttons sit on top of it)
        self.btn_resume = GlassButton(self, "flat", 50, radius=14, width=100)
        self.btn_resume.hide()
        self.btn_resume.clicked.connect(self._resume_clicked)
        self.btn_open = _OpenButton(self)
        self.btn_open.clicked.connect(self.open_requested.emit)
        self.btn_go = GlassButton(self, "disc", GO_D, 22, shadow=False)
        self.btn_go.setIcon(get_svg_icon("play_glass", size=22, color="#F2FBFF"))
        self.btn_go.setToolTip("이어서 재생")
        self.btn_go.hide()
        self.btn_go.clicked.connect(self._resume_clicked)
        self.btn_copy = _LinkButton("진단 정보 복사", self)
        self.btn_copy.hide()
        self.btn_copy.clicked.connect(self.copy_requested.emit)
        self.hide()

    # --- state ---------------------------------------------------------------------------------
    def set_resume(self, path: str, position: float, duration: float):
        """The video to go on with (its saved position and length; 0 when unknown)."""
        near_end = duration > 0 and position >= duration - 3.0
        continuing = position > RESUME_MIN_SECONDS and not near_end
        if continuing:
            time_text = f"{format_time(position)} / {format_time(duration)}" if duration > 0 else format_time(position)
            ratio = (position / duration) if duration > 0 else 0.0
        else:
            time_text = format_time(duration) if duration > 0 else ""
            ratio = 0.0
        self._resume = {"path": path, "name": os.path.basename(path), "label": "이어보기" if continuing else "최근 영상",
                        "time": time_text, "ratio": max(0.0, min(1.0, ratio))}
        self._apply_resume_ui()

    def clear_resume(self):
        self._resume = None
        self._apply_resume_ui()

    def has_resume(self) -> bool:
        return self._resume is not None

    def resume_info(self) -> dict:
        return dict(self._resume) if self._resume else {}

    def set_problem(self, title: str, hint: str):
        """Show why the last file could not be opened (until clear_problem)."""
        self._problem = (title, hint)
        self.btn_copy.show()
        self._layout_problem()
        self.update()

    def clear_problem(self):
        self._problem = None
        self.btn_copy.hide()
        self.update()

    def has_problem(self) -> bool:
        return self._problem is not None

    def problem_title(self) -> str:
        return self._problem[0] if self._problem else ""

    def set_dragging(self, dragging: bool):
        """A file is being dragged over the window: the frame lights up."""
        if dragging != self._dragging:
            self._dragging = dragging
            self.update()

    def is_dragging(self) -> bool:
        return self._dragging

    def _apply_resume_ui(self):
        has = self._resume is not None
        self.btn_resume.setVisible(has)
        self.btn_go.setVisible(has)
        if has:
            self.btn_resume.setToolTip(self._resume["path"])
        self._layout_dock()
        self.update()

    def _resume_clicked(self):
        if self._resume and os.path.exists(self._resume["path"]):
            self.resume_requested.emit(self._resume["path"])

    # --- geometry ------------------------------------------------------------------------------
    def dock_rect(self) -> QRectF:
        w, h = self.width(), self.height()
        if self._resume:
            dw = max(DOCK_MIN_W, min(DOCK_MAX_W, w - 2 * DOCK_SIDE))
        else:
            dw = OPEN_W + 2 * DOCK_PAD
        dw = min(dw, max(120, w - 24))
        return QRectF((w - dw) / 2.0, h - DOCK_BOTTOM - DOCK_H, dw, DOCK_H)

    def _layout_dock(self):
        d = self.dock_rect()
        self.btn_open.move(round(d.left() + DOCK_PAD), round(d.top() + (DOCK_H - OPEN_H) / 2))
        if self._resume:
            go_x = round(d.right() - DOCK_PAD - GO_D)
            self.btn_go.move(go_x, round(d.top() + (DOCK_H - GO_D) / 2))
            left = self.btn_open.x() + self.btn_open.width() + 10
            self.btn_resume.setFixedSize(max(40, go_x - 6 - left), 50)
            self.btn_resume.move(left, round(d.top() + 9))
            self.btn_resume.raise_()
            self.btn_open.raise_()
            self.btn_go.raise_()

    # --- the logo group: logo, name, version, then the hint line or the notice -------------------
    def _notice_metrics(self, w: float):
        """(card width, text width, title height, hint height) of the notice."""
        card_w = min(NOTICE_MAX_W, max(200.0, w - 80))
        text_w = card_w - 2 * NOTICE_PAD - NOTICE_ICON - 12
        hint_h = QFontMetrics(self._font(12)).boundingRect(QRect(0, 0, int(text_w), 1000), Qt.TextWordWrap,
                                                          self._problem[1]).height()
        return card_w, text_w, 20.0, float(hint_h)

    def _group(self) -> dict:
        w, h = self.width(), self.height()
        dock = self.dock_rect()
        area_top, area_bottom = TOP_SAFE, dock.top() - 20
        area_h = max(60.0, area_bottom - area_top)
        size = max(56.0, min(130.0, area_h * 0.42))
        name_h, version_h, hint_h = 26.0, 14.0, 18.0
        g = {"w": w, "dock": dock, "name_h": name_h, "version_h": version_h, "hint_h": hint_h, "show_name": True}
        below = hint_h
        if self._problem:
            card_w, text_w, title_h, body_h = self._notice_metrics(w)
            card_h = NOTICE_PAD * 0.9 + title_h + 5 + body_h + 8 + 20 + NOTICE_PAD * 0.9
            below = card_h
            g.update(card_w=card_w, text_w=text_w, title_h=title_h, body_h=body_h, card_h=card_h)
            # the notice is tall; in a small window the logo gives way first, then the name and the version
            with_logo = 18 + name_h + 4 + version_h + 20 + below
            without_logo = name_h + 4 + version_h + 20 + below
            if area_h - with_logo >= 40:
                size = min(size, area_h - with_logo)
            elif area_h >= without_logo:
                size = 0.0
            else:
                size = 0.0
                g["show_name"] = False
                area_top, area_bottom = 34.0, dock.top() - 8     # (the middle of the title bar is empty: use it)
                area_h = max(60.0, area_bottom - area_top)
        name_block = (name_h + 4 + version_h + 20) if g["show_name"] else 0.0
        logo_block = (size + 18) if size > 0 else 0.0
        group_h = logo_block + name_block + below
        y = area_top + max(0.0, (area_h - group_h) / 2.0)
        g["size"] = size
        g["logo_y"] = y
        g["name_y"] = y + logo_block
        g["version_y"] = g["name_y"] + name_h + 4
        g["below_y"] = y + logo_block + name_block
        return g

    def _layout_problem(self):
        if not self._problem:
            return
        g = self._group()
        text_x = (self.width() - g["card_w"]) / 2.0 + NOTICE_PAD + NOTICE_ICON + 12
        y = g["below_y"] + NOTICE_PAD * 0.9 + g["title_h"] + 5 + g["body_h"] + 8
        self.btn_copy.move(round(text_x), round(y))
        self.btn_copy.raise_()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._layout_dock()
        self._layout_problem()

    # --- mouse: plain clicks / drags / the menu belong to the viewport underneath ----------------
    def mousePressEvent(self, event):
        event.ignore()

    def mouseMoveEvent(self, event):
        event.ignore()

    def mouseReleaseEvent(self, event):
        event.ignore()

    def mouseDoubleClickEvent(self, event):
        event.ignore()

    def contextMenuEvent(self, event):
        event.ignore()

    # --- painting ------------------------------------------------------------------------------
    def _font(self, px: int, weight=QFont.Normal, spacing: float = 0.0) -> QFont:
        f = QFont(self.font())
        f.setPixelSize(px)
        f.setWeight(weight)
        if spacing:
            f.setLetterSpacing(QFont.AbsoluteSpacing, spacing)
        return f

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setRenderHint(QPainter.SmoothPixmapTransform, True)
        w, h = self.width(), self.height()
        dock = self.dock_rect()

        # backdrop: a very soft light behind the logo, fading to black at the edges
        bg = QRadialGradient(QPointF(w / 2.0, h * 0.36), max(w, h) * 0.58)
        bg.setColorAt(0.0, BG_CENTER)
        bg.setColorAt(0.72, BG_MID)
        bg.setColorAt(1.0, BG_EDGE)
        p.fillRect(self.rect(), QBrush(bg))

        # logo, name and hint (or the notice), centred in the room above the dock
        g = self._group()
        size, y = g["size"], g["logo_y"]
        if size > 0:
            p.drawPixmap(QRectF((w - size) / 2.0, y, size, size), self._logo, QRectF(self._logo.rect()))
        if g["show_name"]:
            p.setFont(self._font(22, QFont.Medium, 4.4))
            p.setPen(QColor(255, 255, 255, 224))
            p.drawText(QRectF(0, g["name_y"], w, g["name_h"]), Qt.AlignHCenter | Qt.AlignVCenter, "PANE")
            p.setFont(self._font(11, QFont.Normal, 1.0))
            p.setPen(QColor(255, 255, 255, 72))
            p.drawText(QRectF(0, g["version_y"], w, g["version_h"]), Qt.AlignHCenter | Qt.AlignVCenter, VERSION_TEXT)
        if self._problem:
            self._paint_notice(p, g)
        else:
            p.setFont(self._font(13))
            p.setPen(QColor(255, 255, 255, 214 if self._dragging else 92))
            p.drawText(QRectF(0, g["below_y"], w, g["hint_h"]), Qt.AlignHCenter | Qt.AlignVCenter,
                       HINT_DROP if self._dragging else HINT)

        # the dock
        paint_glass_panel(p, dock, 24, calm=True)
        if self._resume:
            self._paint_resume(p, dock)

        # drag-over frame
        if self._dragging:
            frame = QRectF(28, TOP_SAFE, w - 56, h - TOP_SAFE - 28)
            for width, alpha in ((14, 14), (7, 28)):
                p.setPen(QPen(QColor(255, 255, 255, alpha), width))
                p.setBrush(Qt.NoBrush)
                p.drawRoundedRect(frame, 26, 26)
            p.setPen(QPen(QColor(255, 255, 255, 200), 2.4))
            p.drawRoundedRect(frame, 26, 26)

    def _paint_notice(self, p: QPainter, g: dict):
        title, hint = self._problem
        card = QRectF((g["w"] - g["card_w"]) / 2.0, g["below_y"], g["card_w"], g["card_h"])
        p.setPen(QPen(QColor(WARN.red(), WARN.green(), WARN.blue(), 86), 1))
        p.setBrush(QColor(WARN.red(), WARN.green(), WARN.blue(), 23))
        p.drawRoundedRect(card, 16, 16)
        pad_y = NOTICE_PAD * 0.9
        ix, iy = card.left() + NOTICE_PAD, card.top() + pad_y
        tri = QPainterPath()                                         # the warning triangle
        k = NOTICE_ICON / 24.0
        tri.moveTo(ix + 12 * k, iy + 3 * k)
        tri.lineTo(ix + 22 * k, iy + 20 * k)
        tri.lineTo(ix + 2 * k, iy + 20 * k)
        tri.closeSubpath()
        pen = QPen(WARN, 2.0 * k)
        pen.setJoinStyle(Qt.RoundJoin)
        pen.setCapStyle(Qt.RoundCap)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        p.drawPath(tri)
        p.drawLine(QPointF(ix + 12 * k, iy + 10 * k), QPointF(ix + 12 * k, iy + 14.5 * k))
        p.drawPoint(QPointF(ix + 12 * k, iy + 17.2 * k))
        text_x = ix + NOTICE_ICON + 12
        title_font = self._font(13, QFont.DemiBold)
        p.setFont(title_font)
        p.setPen(WARN_TEXT)
        elided = QFontMetrics(title_font).elidedText(title, Qt.ElideMiddle, int(g["text_w"]))
        p.drawText(QRectF(text_x, card.top() + pad_y, g["text_w"], g["title_h"]), Qt.AlignLeft | Qt.AlignVCenter, elided)
        p.setFont(self._font(12))
        p.setPen(QColor(255, 255, 255, 164))
        p.drawText(QRectF(text_x, card.top() + pad_y + g["title_h"] + 5, g["text_w"], g["body_h"]),
                   Qt.AlignLeft | Qt.AlignTop | Qt.TextWordWrap, hint)

    def _paint_resume(self, p: QPainter, dock: QRectF):
        r = self._resume
        sep_x = self.btn_open.x() + self.btn_open.width() + 10 + 0.5
        p.setPen(QPen(QColor(255, 255, 255, 31), 1))
        p.drawLine(QPointF(sep_x, dock.center().y() - 15), QPointF(sep_x, dock.center().y() + 15))

        go_x = self.btn_go.x()
        time_font = self._font(12, QFont.DemiBold)
        time_w = QFontMetrics(time_font).horizontalAdvance(r["time"]) if r["time"] else 0
        time_right = go_x - 14
        text_left = sep_x + 18
        text_right = time_right - (time_w + 16 if time_w else 0)
        text_w = max(20.0, text_right - text_left)

        p.setFont(self._font(11))
        p.setPen(QColor(255, 255, 255, 128))
        p.drawText(QRectF(text_left, dock.top() + 13, text_w, 14), Qt.AlignLeft | Qt.AlignVCenter, r["label"])
        name_font = self._font(13, QFont.DemiBold)
        p.setFont(name_font)
        p.setPen(QColor(255, 255, 255, 240))
        p.drawText(QRectF(text_left, dock.top() + 28, text_w, 18), Qt.AlignLeft | Qt.AlignVCenter,
                   QFontMetrics(name_font).elidedText(r["name"], Qt.ElideMiddle, int(text_w)))
        if r["ratio"] > 0:
            track = QRectF(text_left, dock.top() + 51, text_w, 2)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(255, 255, 255, 31))
            p.drawRoundedRect(track, 1, 1)
            p.setBrush(QColor(255, 255, 255, 217))
            p.drawRoundedRect(QRectF(track.x(), track.y(), track.width() * r["ratio"], track.height()), 1, 1)
        if r["time"]:
            p.setFont(time_font)
            p.setPen(QColor(255, 255, 255, 191))
            p.drawText(QRectF(time_right - time_w - 2, dock.top() + 20, time_w + 2, 28), Qt.AlignRight | Qt.AlignVCenter, r["time"])
