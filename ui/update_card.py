"""
The update notice: a small glass card in the bottom right corner of the window, above the controls (or above the
start screen's dock), like the next-video card. One card, five states:

    offer       "새 버전 1.3.0 / 지금 업데이트할까요?"   [업데이트] [✕]     (the release notes are its tooltip)
    progress    "새 버전 1.3.0 받는 중 / 29MB / 70MB · 41%" and a thin bar  (nothing to press)
    installing  "설치를 시작했어요 / 잠시 후 Pane이 다시 시작돼요"
    failed      "업데이트하지 못했어요 / <why>"          [다시 시도] [✕]
    hidden

The window decides when it may be seen (not while a video plays, see MainWindow._refresh_update_card); the card only
draws itself and reports the two choices: ``update_clicked`` and ``dismissed``.
"""
from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import QWidget

from ui.glass_button import GlassButton, paint_glass_panel
from ui.icons import get_svg_icon

FONT = "Segoe UI Variable Text"


class UpdateCard(QWidget):
    update_clicked = Signal()
    dismissed = Signal()

    WIDTH, HEIGHT = 320, 64
    PAD = 14
    ICON = 30
    TEXT_LEFT = 54

    def __init__(self, parent):
        super().__init__(parent)
        self.setFixedSize(self.WIDTH, self.HEIGHT)
        self.mode = "hidden"
        self._version = ""
        self._title = ""
        self._detail = ""
        self._fraction = 0.0

        self.btn_close = GlassButton(self, "flat", 24, icon_px=10, radius=12, calm=True)
        self.btn_close.setIcon(get_svg_icon("close", size=10, color="#FFFFFF"))
        self.btn_close.setToolTip("이 버전은 그만 알리기")
        self.btn_close.clicked.connect(self.dismissed)
        self.btn_update = GlassButton(self, "pill", 28, text_px=12, text_pad=12, calm=True, bold=True)
        self.btn_update.setText("업데이트")
        self.btn_update.clicked.connect(self.update_clicked)
        self._layout_buttons()
        self.hide()

    @property
    def title_text(self) -> str:
        return self._title

    @property
    def detail_text(self) -> str:
        return self._detail

    # --- states ---------------------------------------------------------------------------------
    def show_offer(self, version: str, notes: str = ""):
        self._version = version
        self._set("offer", f"새 버전 {version}", "지금 업데이트할까요?", buttons=True, update_label="업데이트")
        self.setToolTip(notes)

    def show_progress(self, done: int, total: int):
        self._fraction = max(0.0, min(1.0, done / total)) if total else 0.0
        self._set("progress", f"새 버전 {self._version} 받는 중",
                  f"{done / 1e6:.0f}MB / {total / 1e6:.0f}MB · {int(self._fraction * 100)}%", buttons=False)

    def show_installing(self):
        self._set("installing", "설치를 시작했어요", "잠시 후 Pane이 다시 시작돼요", buttons=False)

    def show_failure(self, message: str):
        self._set("failed", "업데이트하지 못했어요", message, buttons=True, update_label="다시 시도")

    def hide_card(self):
        self.mode = "hidden"
        self.hide()

    def _set(self, mode: str, title: str, detail: str, buttons: bool, update_label: str = None):
        self.mode, self._title, self._detail = mode, title, detail
        if update_label:
            self.btn_update.setText(update_label)
            self._layout_buttons()
        self.btn_update.setVisible(buttons)
        self.btn_close.setVisible(buttons)
        if not self.isVisible():
            self.show()
            self.raise_()
        self.update()

    def _layout_buttons(self):
        self.btn_close.move(self.WIDTH - 10 - self.btn_close.width(), (self.HEIGHT - self.btn_close.height()) // 2)
        self.btn_update.move(self.btn_close.x() - 6 - self.btn_update.width(), (self.HEIGHT - self.btn_update.height()) // 2)

    def _text_right(self) -> int:
        return (self.btn_update.x() - 8) if self.btn_update.isVisible() else self.WIDTH - self.PAD

    # --- painting -------------------------------------------------------------------------------
    def paintEvent(self, event):
        if self.mode == "hidden":
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        paint_glass_panel(p, QRectF(self.rect()), 16, calm=True)
        self._paint_icon(p)

        right = self._text_right()
        width = max(0, right - self.TEXT_LEFT)
        bar = self.mode == "progress"
        top = 12 if bar else 13
        title_font = QFont(FONT)
        title_font.setPixelSize(13)
        title_font.setWeight(QFont.DemiBold)
        p.setFont(title_font)
        p.setPen(QColor(255, 255, 255, 240))
        p.drawText(QRectF(self.TEXT_LEFT, top, width, 18), Qt.AlignLeft | Qt.AlignVCenter,
                   QFontMetrics(title_font).elidedText(self._title, Qt.ElideRight, width))
        detail_font = QFont(FONT)
        detail_font.setPixelSize(11)
        p.setFont(detail_font)
        p.setPen(QColor(255, 255, 255, 140))
        p.drawText(QRectF(self.TEXT_LEFT, top + 19, width, 16), Qt.AlignLeft | Qt.AlignVCenter,
                   QFontMetrics(detail_font).elidedText(self._detail, Qt.ElideRight, width))
        if bar:
            track = QRectF(self.TEXT_LEFT, self.HEIGHT - 13, width, 4)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(255, 255, 255, 46))
            p.drawRoundedRect(track, 2, 2)
            p.setBrush(QColor(255, 255, 255, 240))
            p.drawRoundedRect(QRectF(track.left(), track.top(), track.width() * self._fraction, track.height()), 2, 2)

    def _paint_icon(self, p: QPainter):
        """A ring with an arrow: up for an offer, down while it downloads or installs."""
        box = QRectF(self.PAD, (self.HEIGHT - self.ICON) / 2.0, self.ICON, self.ICON)
        p.setPen(QPen(QColor(255, 255, 255, 100), 1))
        p.setBrush(QColor(255, 255, 255, 26))
        p.drawEllipse(box)
        c = box.center()
        down = self.mode in ("progress", "installing")
        pen = QPen(QColor(255, 255, 255, 240), 2.0)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        d = 1 if down else -1
        p.drawLine(QPointF(c.x(), c.y() - 6 * d), QPointF(c.x(), c.y() + 6 * d))
        p.drawLine(QPointF(c.x() - 5, c.y() + 1 * d), QPointF(c.x(), c.y() + 6 * d))
        p.drawLine(QPointF(c.x() + 5, c.y() + 1 * d), QPointF(c.x(), c.y() + 6 * d))
