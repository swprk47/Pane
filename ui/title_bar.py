import ctypes
from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel, QPushButton, QApplication
from PySide6.QtCore import Qt, QPoint, Signal, QSize
from ui.icons import get_svg_icon, get_logo_icon
from ui.glass_button import GlassButton


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
        self._press_pos = None
        self._drag_started = False

        self._init_ui()

    def _init_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 0, 10, 0)
        layout.setSpacing(10)

        # App Logo (Modern Vector Icon)
        self.logo_btn = QPushButton(self)
        self.logo_btn.setFocusPolicy(Qt.NoFocus)
        self.logo_btn.setCursor(Qt.PointingHandCursor)
        self.logo_btn.setIcon(get_logo_icon(20))
        self.logo_btn.setIconSize(QSize(20, 20))
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
        self.btn_pip = GlassButton(self, "pill", 22, text_px=11, text_pad=9, tint=True)
        self.btn_pip.setText("PIP")
        self.btn_pip.setObjectName("PipBadgeButton")
        self.btn_pip.setToolTip("PIP 항상 위 미니 모드 (P)")
        self.btn_pip.clicked.connect(self.pip_toggled.emit)
        layout.addWidget(self.btn_pip)

        # Minimize Button (SVG)
        self.btn_min = GlassButton(self, "flat", 28, icon_px=12, radius=8)
        self.btn_min.setIcon(get_svg_icon("minimize", size=12))
        self.btn_min.setToolTip("최소화")
        self.btn_min.clicked.connect(self._minimize_window)
        layout.addWidget(self.btn_min)

        # Maximize / Restore Button (SVG)
        self.btn_max = GlassButton(self, "flat", 28, icon_px=12, radius=8)
        self.btn_max.setIcon(get_svg_icon("maximize", size=12))
        self.btn_max.setToolTip("최대화 / 이전 크기")
        self.btn_max.clicked.connect(self._toggle_maximize)
        layout.addWidget(self.btn_max)

        # Close Button (SVG)
        self.btn_close = GlassButton(self, "flat", 28, icon_px=12, radius=8, danger=True)
        self.btn_close.setIcon(get_svg_icon("close", size=12))
        self.btn_close.setToolTip("닫기")
        self.btn_close.clicked.connect(self._on_close_clicked)
        layout.addWidget(self.btn_close)

    def set_pip_active(self, active: bool):
        """Highlight the PIP badge without replacing its own stylesheet."""
        self.btn_pip.setProperty("active", "true" if active else "false")
        self.btn_pip.setActive(active)

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
    # The native move loop must only start once the cursor really drags. Starting it on
    # press swallows the button-up, so a double-click (maximize/restore) never arrives.

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._press_pos = event.position().toPoint()
            self._drag_started = False
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if (event.buttons() & Qt.LeftButton and self._press_pos is not None and not self._drag_started
                and not self.parent_window.isMaximized()):
            moved = (event.position().toPoint() - self._press_pos).manhattanLength()
            if moved >= QApplication.startDragDistance():
                self._drag_started = True
                native_start_window_drag(int(self.parent_window.winId()))
                event.accept()
                return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._press_pos = None
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._press_pos = None
            self._toggle_maximize()
            event.accept()
