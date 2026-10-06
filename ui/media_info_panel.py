from html import escape

from PySide6.QtWidgets import QFrame, QVBoxLayout, QHBoxLayout, QLabel, QApplication
from PySide6.QtGui import QPainter
from ui.glass_button import GlassButton, paint_glass_panel
from PySide6.QtCore import Qt, QTimer, QRectF

from core.media_info import describe, to_plain_text
from ui.icons import get_svg_icon

WARN = "#FFB340"
GPU_OK = "#5FD68A"      # hardware decoding: the one green on the panel


class MediaInfoPanel(QFrame):
    """
    Glass panel with codec / decoder / stream details of the playing media.
    Refreshes once a second while visible, so it also shows live frame stats.
    `set_provider(fn)`: fn() -> dict as returned by PlayerEngine.get_media_info().
    """
    WIDTH = 392

    def paintEvent(self, event):
        p = QPainter(self)
        paint_glass_panel(p, QRectF(self.rect()), 18)

    def __init__(self, parent):
        super().__init__(parent)
        self.setObjectName("MediaInfoPanel")
        self.setFixedWidth(self.WIDTH)
        self._provider = None
        self._sections = []

        self.setStyleSheet("""
            QLabel { background: transparent; color: #FFFFFF;
                     font-family: "Segoe UI Variable Text", "Segoe UI", sans-serif; }
        """)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 14, 18, 16)
        lay.setSpacing(10)

        header = QHBoxLayout()
        header.setSpacing(8)
        title = QLabel("재생 정보", self)
        title.setStyleSheet("font-size: 14px; font-weight: 700;")
        header.addWidget(title)
        header.addStretch()

        self.btn_copy = GlassButton(self, "pill", 26, text_px=12, text_pad=12)
        self.btn_copy.setText("복사")
        self.btn_copy.setToolTip("이 정보를 텍스트로 복사")
        self.btn_copy.clicked.connect(self.copy_to_clipboard)
        header.addWidget(self.btn_copy)

        self.btn_close = GlassButton(self, "flat", 26, icon_px=10, radius=13, danger=True)
        self.btn_close.setIcon(get_svg_icon("close", size=10))
        self.btn_close.setToolTip("닫기 (I)")
        self.btn_close.clicked.connect(self.hide)
        header.addWidget(self.btn_close)
        lay.addLayout(header)

        self.body = QLabel(self)
        self.body.setTextFormat(Qt.RichText)
        self.body.setWordWrap(True)
        self.body.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        lay.addWidget(self.body)

        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self.refresh)

        self.hide()  # last: hideEvent uses the timer

    # --- data ---------------------------------------------------------------

    def set_provider(self, provider):
        self._provider = provider

    def refresh(self):
        if self._provider is None:
            return
        try:
            self._sections = describe(self._provider())
        except Exception as e:
            self._sections = [("오류", [("정보를 읽지 못했습니다", str(e))])]
        self.body.setText(self._to_html(self._sections))
        self.adjustSize()

    def plain_text(self) -> str:
        return to_plain_text(self._sections)

    def copy_to_clipboard(self):
        QApplication.clipboard().setText(self.plain_text())
        self.btn_copy.setText("복사됨")
        QTimer.singleShot(1200, lambda: self.btn_copy.setText("복사"))

    @staticmethod
    def _value_html(label: str, value: str) -> str:
        text = escape(value)
        if label == "디코더":
            color = GPU_OK if value.startswith("GPU") else WARN
            return f'<span style="color:{color}; font-weight:600">{text}</span>'
        if label == "버려진 프레임" and not value.startswith("0 "):
            return f'<span style="color:{WARN}; font-weight:600">{text}</span>'
        return text

    def _to_html(self, sections) -> str:
        parts = ['<table cellspacing="0" cellpadding="2" style="font-size:12px">']
        for i, (title, rows) in enumerate(sections):
            pad = "" if i == 0 else "padding-top:8px;"
            parts.append(f'<tr><td colspan="2" style="{pad} color:rgba(255,255,255,0.62); font-size:11px; font-weight:700">{escape(title)}</td></tr>')
            for label, value in rows:
                parts.append(
                    f'<tr><td width="92" style="color:rgba(255,255,255,0.55)">{escape(label)}</td>'
                    f'<td>{self._value_html(label, value)}</td></tr>')
        parts.append("</table>")
        return "".join(parts)

    # --- visibility -----------------------------------------------------------

    def showEvent(self, event):
        super().showEvent(event)
        self.refresh()
        self._timer.start()

    def hideEvent(self, event):
        super().hideEvent(event)
        self._timer.stop()
