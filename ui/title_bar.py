import ctypes
from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel, QPushButton, QApplication, QGraphicsOpacityEffect, QFrame
from PySide6.QtCore import Qt, Signal, QSize, QVariantAnimation, QEasingCurve
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


class SpinButton(GlassButton):
    """A glass button whose icon can turn round and round (while something is being waited for). When told to stop it
    finishes the turn it is in, so the icon always comes to rest upright."""
    TURN_MS = 900

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._angle = 0.0
        self._spin = QVariantAnimation(self)
        self._spin.setStartValue(0.0)
        self._spin.setEndValue(360.0)
        self._spin.setDuration(self.TURN_MS)
        self._spin.setEasingCurve(QEasingCurve.Linear)
        self._spin.setLoopCount(-1)
        self._spin.valueChanged.connect(self._on_angle)
        self._spin.finished.connect(self._on_spin_finished)

    @property
    def spinning(self) -> bool:
        return self._spin.state() == QVariantAnimation.Running

    def angle(self) -> float:
        return self._angle

    def set_spinning(self, on: bool):
        if on:
            self._spin.setLoopCount(-1)
            if not self.spinning:
                self._spin.start()
        elif self.spinning:
            self._spin.setLoopCount(self._spin.currentLoop() + 1)     # (the turn it is in is the last one)

    def _on_angle(self, value):
        self._angle = float(value)
        self.update()

    def _on_spin_finished(self):
        self._angle = 0.0
        self.update()

    def _draw_icon(self, p, icon, opacity, scale=1.0):
        if not self._angle:
            return super()._draw_icon(p, icon, opacity, scale)
        p.save()
        p.translate(self.width() / 2.0, self.height() / 2.0)
        p.rotate(self._angle)
        p.translate(-self.width() / 2.0, -self.height() / 2.0)
        super()._draw_icon(p, icon, opacity, scale)
        p.restore()


class GlassTitleBar(QWidget):
    """
    Apple Glass-styled custom frameless title bar that floats over the top of the video.
    It paints no background of its own (the top scrim behind it supplies the shade) and fades together with
    the controls; while it is faded out its buttons ignore the mouse, but its empty part still drags the
    window. Uses native Windows dragging and modern SVG vector icons.
    """
    pip_toggled = Signal()
    help_clicked = Signal()             # the 단축키 도움말 button (always there)
    update_clicked = Signal()           # the 업데이트 확인 button (home screen only)
    activity = Signal()                 # the mouse moved over the bar: bring the controls back

    HEIGHT = 38
    shows_restore = False               # the maximize button currently shows 'restore' (the window is maximized)
    INTERACTIVE_ABOVE = 0.25            # buttons only react while the bar is at least this visible

    def __init__(self, parent_window, parent=None):
        super().__init__(parent or parent_window)
        self.parent_window = parent_window
        self.setObjectName("GlassTitleBar")
        self.setFixedHeight(self.HEIGHT)
        self.setMouseTracking(True)
        self._press_pos = None
        self._drag_started = False
        self._interactive = True
        self._fx = QGraphicsOpacityEffect(self)
        self._fx.setOpacity(1.0)
        self.setGraphicsEffect(self._fx)

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

        layout.addStretch()

        # PIP Button (Clean Text Capsule instead of Pin emoji)
        self.btn_pip = GlassButton(self, "pill", 22, text_px=11, text_pad=9, tint=True)
        self.btn_pip.setText("PIP")
        self.btn_pip.setObjectName("PipBadgeButton")
        self.btn_pip.setToolTip("PIP 항상 위 미니 모드 (P)")
        self.btn_pip.clicked.connect(self.pip_toggled.emit)
        layout.addWidget(self.btn_pip)

        # Check for a new version (the home screen only; turns while it waits), then a divider before the window buttons
        self.btn_update = SpinButton(self, "flat", 28, icon_px=13, radius=8)
        self.btn_update.setIcon(get_svg_icon("refresh", size=13))
        self.btn_update.setToolTip("업데이트 확인")
        self.btn_update.clicked.connect(self.update_clicked.emit)
        layout.addWidget(self.btn_update)
        self.btn_help = GlassButton(self, "flat", 28, icon_px=14, radius=8)
        self.btn_help.setIcon(get_svg_icon("help", size=14))
        self.btn_help.setToolTip("단축키 도움말 (?)")
        self.btn_help.clicked.connect(self.help_clicked.emit)
        layout.addWidget(self.btn_help)
        self.sep_update = QFrame(self)
        self.sep_update.setFixedSize(1, 16)
        self.sep_update.setStyleSheet("background: rgba(255, 255, 255, 0.22); border: none;")
        layout.addWidget(self.sep_update)

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

    def _buttons(self):
        return (self.logo_btn, self.btn_pip, self.btn_update, self.btn_help, self.btn_min, self.btn_max, self.btn_close)

    def set_update_visible(self, visible: bool):
        """The update button belongs to the home screen: out of the way while a video is open (the divider stays)."""
        self.btn_update.setVisible(visible)

    def set_opacity(self, value: float):
        value = max(0.0, min(1.0, value))
        self._fx.setOpacity(value)
        interactive = value >= self.INTERACTIVE_ABOVE
        if interactive != self._interactive:
            self._interactive = interactive
            for b in self._buttons():                  # an invisible close button must not be clickable
                b.setAttribute(Qt.WA_TransparentForMouseEvents, not interactive)

    def opacity(self) -> float:
        return self._fx.opacity()

    def set_pip_active(self, active: bool):
        """Highlight the PIP badge without replacing its own stylesheet."""
        self.btn_pip.setProperty("active", "true" if active else "false")
        self.btn_pip.setActive(active)

    def sync_maximized(self, maximized: bool):
        """The maximize button shows 'restore' while the window is maximized (however that happened)."""
        self.shows_restore = bool(maximized)
        self.btn_max.setIcon(get_svg_icon("restore" if maximized else "maximize", size=12))

    def _toggle_maximize(self):
        if self.parent_window.isMaximized():
            self.parent_window.showNormal()
        else:
            self.parent_window.showMaximized()
        self.sync_maximized(self.parent_window.isMaximized())

    def _minimize_window(self):
        self.parent_window.showMinimized()

    def _close_window(self):
        self.parent_window.close()

    def _on_close_clicked(self):
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
        self.activity.emit()
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
