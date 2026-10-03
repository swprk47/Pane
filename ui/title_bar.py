import ctypes
from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel, QPushButton
from PySide6.QtCore import Qt, QPoint, Signal, QSize
from ui.icons import get_svg_icon


def native_start_window_drag(hwnd):
    """Trigger Windows native window drag with zero latency and Aero Snap support."""
    try:
        ctypes.windll.user32.ReleaseCapture()
        # WM_NCLBUTTONDOWN = 0x00A1, HTCAPTION = 2
        ctypes.windll.user32.SendMessageW(hwnd, 0x00A1, 2, 0)
        return True
    except Exception:
        return False


class GlassTitleBar(QWidget):
    """
    Apple Glass-styled custom frameless title bar.
    Uses native Windows dragging and modern SVG vector icons.
    """
    pip_toggled = Signal()
    close_requested = Signal()

    def __init__(self, parent_window):
        super().__init__(parent_window)
        self.parent_window = parent_window
        self.setObjectName("GlassTitleBar")
        # Needed for the #GlassTitleBar QSS background to paint; otherwise the
        # bar is alpha 0 and clicks fall through the translucent window.
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setFixedHeight(38)

        self._init_ui()

    def _init_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 0, 10, 0)
        layout.setSpacing(10)

        # App Logo (Modern Vector Icon)
        self.logo_btn = QPushButton(self)
        self.logo_btn.setFocusPolicy(Qt.NoFocus)
        self.logo_btn.setCursor(Qt.PointingHandCursor)
        self.logo_btn.setIcon(get_svg_icon("play", size=14, color="#0A84FF"))
        self.logo_btn.setIconSize(QSize(14, 14))
        self.logo_btn.setStyleSheet("background: transparent; border: none; padding: 0;")
        layout.addWidget(self.logo_btn)

        # App Title
        self.title_label = QLabel("Pane", self)
        self.title_label.setObjectName("TitleLabel")
        layout.addWidget(self.title_label)

        # Media filename label
        self.file_label = QLabel("", self)
        self.file_label.setObjectName("SubTitleLabel")
        layout.addWidget(self.file_label)

        layout.addStretch()

        # PIP Button (Clean Text Capsule instead of Pin emoji)
        self.btn_pip = QPushButton("PIP", self)
        self.btn_pip.setFocusPolicy(Qt.NoFocus)
        self.btn_pip.setCursor(Qt.PointingHandCursor)
        self.btn_pip.setObjectName("PipBadgeButton")
        self.btn_pip.setToolTip("PIP 항상 위 미니 모드 (P)")
        self.btn_pip.setStyleSheet("""
            QPushButton#PipBadgeButton {
                background: rgba(255, 255, 255, 0.10);
                border: 1px solid rgba(255, 255, 255, 0.18);
                border-radius: 6px;
                color: rgba(255, 255, 255, 0.85);
                font-size: 11px;
                font-weight: 700;
                letter-spacing: 0.5px;
                padding: 3px 8px;
            }
            QPushButton#PipBadgeButton:hover {
                background: rgba(10, 132, 255, 0.35);
                border: 1px solid #0A84FF;
                color: #FFFFFF;
            }
            QPushButton#PipBadgeButton[active="true"] {
                background: #0A84FF;
                border: 1px solid #0A84FF;
                color: #FFFFFF;
            }
            QPushButton#PipBadgeButton:pressed {
                background: rgba(10, 132, 255, 0.70);
                border: 1px solid #70B4FF;
                color: #FFFFFF;
                padding-top: 4px;
                padding-bottom: 2px;
            }
        """)
        self.btn_pip.clicked.connect(self.pip_toggled.emit)
        layout.addWidget(self.btn_pip)

        # Minimize Button (SVG)
        self.btn_min = QPushButton(self)
        self.btn_min.setFocusPolicy(Qt.NoFocus)
        self.btn_min.setCursor(Qt.PointingHandCursor)
        self.btn_min.setProperty("class", "TitleButton")
        self.btn_min.setIcon(get_svg_icon("minimize", size=12))
        self.btn_min.setIconSize(QSize(12, 12))
        self.btn_min.setToolTip("최소화")
        self.btn_min.clicked.connect(self._minimize_window)
        layout.addWidget(self.btn_min)

        # Maximize / Restore Button (SVG)
        self.btn_max = QPushButton(self)
        self.btn_max.setFocusPolicy(Qt.NoFocus)
        self.btn_max.setCursor(Qt.PointingHandCursor)
        self.btn_max.setProperty("class", "TitleButton")
        self.btn_max.setIcon(get_svg_icon("maximize", size=12))
        self.btn_max.setIconSize(QSize(12, 12))
        self.btn_max.setToolTip("최대화 / 이전 크기")
        self.btn_max.clicked.connect(self._toggle_maximize)
        layout.addWidget(self.btn_max)

        # Close Button (SVG)
        self.btn_close = QPushButton(self)
        self.btn_close.setFocusPolicy(Qt.NoFocus)
        self.btn_close.setCursor(Qt.PointingHandCursor)
        self.btn_close.setObjectName("CloseButton")
        self.btn_close.setProperty("class", "TitleButton")
        self.btn_close.setIcon(get_svg_icon("close", size=12))
        self.btn_close.setIconSize(QSize(12, 12))
        self.btn_close.setToolTip("닫기")
        self.btn_close.clicked.connect(self._on_close_clicked)
        layout.addWidget(self.btn_close)

    def set_pip_active(self, active: bool):
        """Highlight the PIP badge without replacing its own stylesheet."""
        self.btn_pip.setProperty("active", "true" if active else "false")
        self.btn_pip.style().unpolish(self.btn_pip)
        self.btn_pip.style().polish(self.btn_pip)

    def set_media_title(self, title: str):
        if title:
            self.file_label.setText(f"· {title}")
        else:
            self.file_label.setText("")

    def _toggle_maximize(self):
        if self.parent_window.isMaximized():
            self.parent_window.showNormal()
            self.btn_max.setIcon(get_svg_icon("maximize", size=12))
        else:
            self.parent_window.showMaximized()
            self.btn_max.setIcon(get_svg_icon("restore", size=12))

    def _minimize_window(self):
        self.parent_window.showMinimized()

    def _close_window(self):
        self.parent_window.close()

    def _on_close_clicked(self):
        self.close_requested.emit()
        self._close_window()

    # --- Windows Native Drag Event ---

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            hwnd = int(self.parent_window.winId())
            if not self.parent_window.isMaximized():
                if native_start_window_drag(hwnd):
                    event.accept()
                    return
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._toggle_maximize()
            event.accept()
