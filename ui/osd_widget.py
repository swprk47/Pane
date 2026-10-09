from PySide6.QtWidgets import QWidget, QLabel, QHBoxLayout, QGraphicsOpacityEffect, QSizePolicy
from PySide6.QtCore import Qt, QTimer, QVariantAnimation, QEasingCurve, QRectF
from PySide6.QtGui import QPainter, QColor, QLinearGradient, QPen
from ui.icons import SVG_ICONS, get_svg_pixmap
from ui.glass_button import ACCENT_TEXT

# Icons that should not use the default (near-white) color.
ICON_COLORS = {"warning": "#FFB340", "volume_mute": "#FF6B61"}
DEFAULT_ICON_COLOR = "#F2FBFF"
SPEED_COLOR = ACCENT_TEXT.name()   # the speed value wears the same accent as the speed button on the controls

PILL_HEIGHT = 42
PAD_LEFT, PAD_RIGHT = 14, 20
TOP_OFFSET = 68                   # the pill's resting top: under the title bar and the file name
SIDE_MARGIN = 28                  # room around the pill for its shadow
BOTTOM_MARGIN = 28
COLLAPSED_W, COLLAPSED_H, COLLAPSED_TOP = 64, 22, 8   # where it starts / ends: a small capsule at the top edge
HOLD_MS = 1000

# Motion: it opens with a slight overshoot that settles (spring-like) and folds back smoothly. The cost of a
# frame is the same whatever the curve (every frame re-composites the window, ~5 ms), so smoothness comes from the
# curve and the length, not from more frames.
OPEN_MS, CLOSE_MS = 460, 300
OPEN_OVERSHOOT = 0.8


def _smooth(x: float, a: float, b: float) -> float:
    t = max(0.0, min(1.0, (x - a) / (b - a)))
    return t * t * (3 - 2 * t)


class GlassOSDWidget(QWidget):
    """
    On-screen notice: a dark glass pill that grows out of the top edge of the window (like a phone's
    dynamic island), shows `icon  text  value` for a second and folds back up. A new message while it is
    up just swaps the content and keeps it open longer.

    Used for the value feedback of keyboard shortcuts (speed, volume, sync ...), for short notices
    (capture saved, subtitle loaded ...) and for warnings.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)

        self._t = 0.0                 # 0: folded into the capsule at the top edge, 1: fully open
        self._anchor = None           # (x centre, top y) in the parent, set by the window
        self._closing = False

        self._init_ui()

        self._anim = QVariantAnimation(self)
        self._anim.valueChanged.connect(self._on_anim_value)
        self._anim.finished.connect(self._on_anim_finished)

        # Timer to hold the open state before folding up
        self.hold_timer = QTimer(self)
        self.hold_timer.setSingleShot(True)
        self.hold_timer.timeout.connect(self._start_close)

        self.hide()

    def _init_ui(self):
        # The content sits in a container that is moved to the middle of the (animated) pill; its own size
        # never changes, so the text is not squeezed while the pill grows.
        self.content = QWidget(self)
        self.content.setAttribute(Qt.WA_TranslucentBackground, True)
        layout = QHBoxLayout(self.content)
        layout.setContentsMargins(PAD_LEFT, 0, PAD_RIGHT, 0)
        layout.setSpacing(9)

        self.icon_label = QLabel("", self.content)
        self.icon_label.setFixedSize(18, 18)
        self.icon_label.setStyleSheet("background: transparent; border: none; margin: 0; padding: 0;")
        layout.addWidget(self.icon_label)

        self.text_label = QLabel("", self.content)
        self.text_label.setObjectName("GlassOSD")
        self.text_label.setStyleSheet("""
            QLabel#GlassOSD {
                font-family: "Segoe UI Variable Text", "Segoe UI", sans-serif;
                font-size: 14px; font-weight: 600; color: #FFFFFF;
                background-color: transparent; border: none; margin: 0; padding: 0;
            }
        """)
        layout.addWidget(self.text_label)

        self.value_label = QLabel("", self.content)
        self.value_label.setObjectName("GlassOSDValue")
        self.value_label.hide()
        layout.addWidget(self.value_label)
        for label in (self.text_label, self.value_label):
            label.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Preferred)      # never stretch: the pill hugs its text

        self._fx = QGraphicsOpacityEffect(self.content)
        self._fx.setOpacity(0.0)
        self.content.setGraphicsEffect(self._fx)

    # --- content ----------------------------------------------------------

    def full_text(self) -> str:
        """What the pill says, e.g. "배속 1.25x"."""
        return " ".join(s for s in (self.text_label.text(), self.value_label.text()) if s)

    def show_message(self, text: str, icon: str = "", value: str = "", accent: bool = False):
        """Show the pill: an optional icon (a key of ui.icons.SVG_ICONS), the text, and an optional value after
        it (`accent`: the value in the app's accent color, used for the speed)."""
        self.text_label.setText(text)
        self.value_label.setText(value)
        self.value_label.setVisible(bool(value))
        self.value_label.setStyleSheet(
            f'QLabel#GlassOSDValue {{ font-family: "Segoe UI Variable Text", "Segoe UI", sans-serif; font-size: 14px;'
            f' font-weight: 700; color: {SPEED_COLOR if accent else "#FFFFFF"}; background: transparent; border: none; margin: 0; padding: 0; }}')
        if icon in SVG_ICONS:
            self.icon_label.setPixmap(get_svg_pixmap(icon, 18, ICON_COLORS.get(icon, DEFAULT_ICON_COLOR)))
            self.icon_label.show()
        else:
            self.icon_label.hide()

        self.text_label.adjustSize()
        self.value_label.adjustSize()
        self.content.layout().activate()
        self.content.resize(self.content.layout().sizeHint())
        self.setFixedSize(self.content.width() + 2 * SIDE_MARGIN, TOP_OFFSET + PILL_HEIGHT + BOTTOM_MARGIN)
        self._place()

        self.hold_timer.stop()
        self.show()
        self.raise_()
        if self._t < 1.0 or self._closing:
            self._animate_to(1.0, OPEN_MS, self._open_curve())
        else:
            self._layout_content()
            self.update()
        self.hold_timer.start(HOLD_MS + (OPEN_MS if self._t < 1.0 else 0))

    # --- placing ----------------------------------------------------------

    def place(self, x_center: int, top: int):
        """Where the window wants the pill: centred on `x_center`, its widget starting at `top`."""
        self._anchor = (x_center, top)
        self._place()

    def _place(self):
        if self._anchor is not None:
            cx, top = self._anchor
        elif self.parent():
            cx, top = self.parent().width() // 2, 0
        else:
            return
        self.move(int(cx - self.width() / 2), int(top))

    # --- animation --------------------------------------------------------

    @staticmethod
    def _open_curve() -> QEasingCurve:
        curve = QEasingCurve(QEasingCurve.OutBack)
        curve.setOvershoot(OPEN_OVERSHOOT)
        return curve

    def _animate_to(self, target: float, ms: int, curve):
        self._closing = target == 0.0
        self._anim.stop()
        self._anim.setStartValue(float(self._t))
        self._anim.setEndValue(float(target))
        self._anim.setDuration(ms)
        self._anim.setEasingCurve(curve)
        self._anim.start()

    def _start_close(self):
        self._animate_to(0.0, CLOSE_MS, QEasingCurve(QEasingCurve.InOutCubic))

    def _on_anim_value(self, value):
        self._t = float(value)
        self._layout_content()
        self.update()

    def _on_anim_finished(self):
        if self._closing and self._t <= 0.001:
            self.hide()
            self._closing = False

    def _pill_rect(self) -> QRectF:
        w_full = self.width() - 2 * SIDE_MARGIN
        t = self._t
        w = COLLAPSED_W + (w_full - COLLAPSED_W) * t
        h = COLLAPSED_H + (PILL_HEIGHT - COLLAPSED_H) * t
        top = COLLAPSED_TOP + (TOP_OFFSET - COLLAPSED_TOP) * t
        return QRectF((self.width() - w) / 2, top, w, h)

    def _layout_content(self):
        r = self._pill_rect()
        c = self.content
        c.move(int(r.center().x() - c.width() / 2), int(r.center().y() - c.height() / 2))
        self._fx.setOpacity(_smooth(self._t, 0.45, 0.85))

    # --- painting ---------------------------------------------------------

    def paintEvent(self, event):
        r = self._pill_rect()
        radius = r.height() / 2
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        fade = _smooth(self._t, 0.0, 0.15)             # the capsule itself fades in as it appears
        p.setOpacity(fade)

        # soft shadow
        p.setPen(Qt.NoPen)
        for grow, alpha in ((14, 10), (9, 16), (5, 22), (2, 28)):
            p.setBrush(QColor(0, 0, 0, alpha))
            p.drawRoundedRect(r.adjusted(-grow, -grow * 0.4 + 3, grow, grow * 0.9 + 3), radius + grow, radius + grow)

        body = QLinearGradient(0, r.top(), 0, r.bottom())
        body.setColorAt(0.0, QColor(0, 0, 0, 184))
        body.setColorAt(1.0, QColor(0, 0, 0, 214))
        p.setBrush(body)
        p.setPen(QPen(QColor(255, 255, 255, 51), 1.5))
        p.drawRoundedRect(r.adjusted(0.75, 0.75, -0.75, -0.75), radius, radius)
