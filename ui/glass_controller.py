import json
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QSlider, QDialog, QListWidget,
    QListWidgetItem, QGraphicsOpacityEffect
)
from PySide6.QtGui import QPainter, QLinearGradient, QColor, QCursor, QMouseEvent, QContextMenuEvent
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt, Signal, QTimer, QEvent, QPropertyAnimation, QEasingCurve, QSettings, QSize
from ui.timeline_slider import TimelineSlider
from ui.volume_popup import VolumePopup
from core.settings import open_settings
from ui.icons import get_svg_icon
from ui.glass_button import GlassButton, DISC_MARGIN

DEFAULT_LAYOUT = {
    "left": ["time_label", "speed_button"],
    "center": ["prev_frame", "seek_backward", "play_pause", "seek_forward", "next_frame"],
    "right": ["screenshot", "subtitle", "volume", "fullscreen", "settings"]
}

# Bump when DEFAULT_LAYOUT changes so stale saved layouts get replaced once.
LAYOUT_VERSION = 3

BUTTON_METADATA = {
    "play_pause": {"name": "재생 / 일시정지", "icon_name": "play"},
    "prev_frame": {"name": "1프레임 이전", "icon_name": "prev_frame"},
    "next_frame": {"name": "1프레임 다음", "icon_name": "next_frame"},
    "seek_backward": {"name": "5초 뒤로", "icon_name": "backward_5"},
    "seek_forward": {"name": "5초 앞으로", "icon_name": "forward_5"},
    "time_label": {"name": "재생 시간 표시", "icon_name": None},
    "speed_button": {"name": "정밀 배속 조절", "icon_name": None},
    "screenshot": {"name": "화면 캡처", "icon_name": "screenshot"},
    "subtitle": {"name": "자막 토글", "icon_name": "subtitle"},
    "volume": {"name": "볼륨 슬라이더", "icon_name": "volume_high"},
    "fullscreen": {"name": "전체화면 토글", "icon_name": "fullscreen"},
    "settings": {"name": "버튼 배열 설정", "icon_name": "settings"}
}


# Transport glass buttons: disc diameter / icon size in px (the widget adds DISC_MARGIN around the disc for the shadow)
PLAY_DISC, PLAY_ICON = 72, 52
SIDE_DISC, SIDE_ICON = 48, 32


class ControllerSettingsDialog(QDialog):
    """
    Glass Dialog to customize button layout for Left, Center, and Right zones.
    """
    layout_changed = Signal(dict)

    def __init__(self, current_layout: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("컨트롤러 버튼 배열 설정")
        self.resize(520, 360)
        self.setStyleSheet("""
            QDialog {
                background-color: rgba(28, 28, 38, 0.98);
                border: 1px solid rgba(255, 255, 255, 0.20);
                border-radius: 16px;
            }
            QLabel {
                color: #FFFFFF;
                font-family: "Segoe UI", sans-serif;
            }
            QListWidget {
                background-color: rgba(18, 18, 24, 0.85);
                border: 1px solid rgba(255, 255, 255, 0.12);
                border-radius: 10px;
                color: #FFFFFF;
                padding: 6px;
            }
            QListWidget::item {
                padding: 6px;
                border-radius: 6px;
            }
            QListWidget::item:selected {
                background-color: rgba(255, 255, 255, 0.18);
            }
            QPushButton {
                background: rgba(255, 255, 255, 0.10);
                border: 1px solid rgba(255, 255, 255, 0.15);
                border-radius: 8px;
                color: #FFFFFF;
                padding: 6px 14px;
            }
            QPushButton:hover {
                background: rgba(255, 255, 255, 0.20);
            }
        """)

        self.layout_data = {
            "left": list(current_layout.get("left", [])),
            "center": list(current_layout.get("center", [])),
            "right": list(current_layout.get("right", []))
        }

        self._init_ui()

    def _init_ui(self):
        vbox = QVBoxLayout(self)
        vbox.setContentsMargins(18, 18, 18, 18)
        vbox.setSpacing(12)

        title = QLabel("컨트롤러 버튼 구역별 배치 설정", self)
        title.setStyleSheet("font-size: 15px; font-weight: bold;")
        vbox.addWidget(title)

        desc = QLabel("각 구역(좌/중/우)에 표시할 버튼을 체크하거나 위/아래로 순서를 이동하세요.", self)
        desc.setStyleSheet("font-size: 12px; color: rgba(255, 255, 255, 0.6);")
        vbox.addWidget(desc)

        cols_layout = QHBoxLayout()
        self.lists = {}

        for zone, title_txt in [("left", "좌측 구역"), ("center", "중앙 구역"), ("right", "우측 구역")]:
            col_box = QVBoxLayout()
            col_lbl = QLabel(title_txt, self)
            col_lbl.setStyleSheet("font-size: 13px; font-weight: 600;")
            col_box.addWidget(col_lbl)

            lw = QListWidget(self)
            self.lists[zone] = lw
            col_box.addWidget(lw)

            btn_row = QHBoxLayout()
            btn_up = QPushButton("▲", self)
            btn_up.clicked.connect(lambda _, z=zone: self._move_item(z, -1))
            btn_down = QPushButton("▼", self)
            btn_down.clicked.connect(lambda _, z=zone: self._move_item(z, 1))
            btn_row.addWidget(btn_up)
            btn_row.addWidget(btn_down)
            col_box.addLayout(btn_row)

            cols_layout.addLayout(col_box)

        vbox.addLayout(cols_layout)
        self._populate_lists()

        bot_layout = QHBoxLayout()
        btn_reset = QPushButton("기본값 복원", self)
        btn_reset.clicked.connect(self._reset_default)
        bot_layout.addWidget(btn_reset)
        bot_layout.addStretch()

        btn_save = QPushButton("적용 및 저장", self)
        btn_save.setStyleSheet("background: rgba(255, 255, 255, 0.20); color: #FFFFFF; border: 1px solid rgba(255, 255, 255, 0.38); font-weight: bold;")
        btn_save.clicked.connect(self._save_and_close)
        bot_layout.addWidget(btn_save)

        vbox.addLayout(bot_layout)

    def _populate_lists(self):
        for zone in ["left", "center", "right"]:
            lw = self.lists[zone]
            lw.clear()
            for key in self.layout_data[zone]:
                meta = BUTTON_METADATA.get(key, {"name": key})
                item = QListWidgetItem(meta['name'])
                if meta.get("icon_name"):
                    item.setIcon(get_svg_icon(meta["icon_name"], size=14))
                item.setData(Qt.UserRole, key)
                item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
                item.setCheckState(Qt.Checked)
                lw.addItem(item)

    def _move_item(self, zone: str, direction: int):
        lw = self.lists[zone]
        row = lw.currentRow()
        if row < 0:
            return
        target_row = row + direction
        if 0 <= target_row < lw.count():
            item = lw.takeItem(row)
            lw.insertItem(target_row, item)
            lw.setCurrentRow(target_row)

    def _reset_default(self):
        self.layout_data = {
            "left": list(DEFAULT_LAYOUT["left"]),
            "center": list(DEFAULT_LAYOUT["center"]),
            "right": list(DEFAULT_LAYOUT["right"])
        }
        self._populate_lists()

    def _save_and_close(self):
        new_layout = {}
        for zone in ["left", "center", "right"]:
            lw = self.lists[zone]
            keys = []
            for i in range(lw.count()):
                item = lw.item(i)
                if item.checkState() == Qt.Checked:
                    keys.append(item.data(Qt.UserRole))
            new_layout[zone] = keys
        self.layout_changed.emit(new_layout)
        self.accept()


class GlassController(QWidget):
    """
    Floating Apple Glass Capsule Controller with modular customizable button layout
    and responsive SVG vector icons.
    """
    play_pause_clicked = Signal()
    prev_frame_clicked = Signal()
    next_frame_clicked = Signal()
    seek_backward_clicked = Signal(float)
    seek_forward_clicked = Signal(float)
    speed_button_clicked = Signal()
    volume_changed = Signal(float)
    mute_clicked = Signal()
    subtitle_clicked = Signal()
    screenshot_clicked = Signal()
    fullscreen_clicked = Signal()
    seek_requested = Signal(float)
    visibility_changed = Signal(bool)   # controls shown / hidden (for the mini progress line)
    opacity_changed = Signal(float)     # follows the fade so the top scrim fades with us

    # Height of the bottom strip that carries the scrim gradient, and of the
    # part of it that counts as "the controls" for hover / auto-hide.
    STRIP_HEIGHT = 230
    CONTROLS_HEIGHT = 140
    SCRIM_ALPHA = 0.85

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("GlassControllerOverlay")
        self.setMinimumHeight(self.CONTROLS_HEIGHT)
        self.forward_target = None   # video viewport: gets clicks on empty areas
        self.hold_visible = None     # callable -> True keeps the controls from auto-hiding
        self._has_media = False

        self.settings = open_settings("ControllerLayout")
        self.current_layout = self._load_layout()

        self._compact = False
        self._is_playing = False
        self._is_muted = False
        self._duration = 0.0
        self._time_pos = 0.0

        self.volume_popup = VolumePopup(parent)
        self.vol_slider = self.volume_popup.slider
        self.volume_popup.value_changed.connect(lambda v: self.volume_changed.emit(float(v)))

        self._init_ui()

        # Fast 120ms animation for instant responsiveness
        self.opacity_effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self.opacity_effect)
        self.opacity_effect.setOpacity(1.0)

        self.fade_anim = QPropertyAnimation(self.opacity_effect, b"opacity")
        self.fade_anim.setDuration(120)
        self.fade_anim.setEasingCurve(QEasingCurve.OutQuad)
        self.fade_anim.finished.connect(self._hide_after_fade)
        self.fade_anim.valueChanged.connect(lambda v: self.opacity_changed.emit(float(v)))

        self.autohide_timer = QTimer(self)
        self.autohide_timer.setInterval(2800)
        self.autohide_timer.setSingleShot(True)
        self.autohide_timer.timeout.connect(self._fade_out)

    def _load_layout(self) -> dict:
        raw = self.settings.value("button_layout", None)
        if int(self.settings.value("layout_version", 0) or 0) != LAYOUT_VERSION:
            raw = None
            self.settings.setValue("layout_version", LAYOUT_VERSION)
            self.settings.remove("button_layout")
        if raw:
            try:
                data = json.loads(raw)
                if isinstance(data, dict):
                    return data
            except Exception:
                pass
        return dict(DEFAULT_LAYOUT)

    def _save_layout(self, layout_dict: dict):
        self.current_layout = layout_dict
        self.settings.setValue("button_layout", json.dumps(layout_dict))
        self._rebuild_buttons()

    def _init_ui(self):
        self.setStyleSheet("""
            /* Overlay style: icons sit directly on the video scrim, no bar. */
            QPushButton {
                background: transparent;
                border: none;
                border-radius: 20px;
                color: #FFFFFF;
                padding: 0px 10px;
                min-width: 20px;
                min-height: 40px;
                max-height: 40px;
                outline: none;
            }
            QPushButton:hover {
                background: rgba(255, 255, 255, 0.16);
            }
            QPushButton:pressed {
                background: rgba(255, 255, 255, 0.26);
            }
            QPushButton#PlayButton {
                background: rgba(255, 255, 255, 0.16);
                border: 1px solid rgba(255, 255, 255, 0.42);
                border-radius: 28px;
                min-width: 36px;
                min-height: 56px;
                max-height: 56px;
            }
            QPushButton#PlayButton:hover {
                background: rgba(255, 255, 255, 0.26);
                border: 1px solid rgba(255, 255, 255, 0.65);
            }
            QPushButton#PlayButton:pressed {
                background: rgba(255, 255, 255, 0.34);
                border: 1px solid rgba(255, 255, 255, 0.8);
            }
            QLabel {
                color: rgba(255, 255, 255, 0.92);
                font-family: "Segoe UI Variable Text", "Segoe UI", sans-serif;
                font-size: 13px;
                background: transparent;
            }
        """)

        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(24, 0, 24, 14)
        self.main_layout.setSpacing(4)
        self.main_layout.addStretch(1)  # content sits at the bottom of the scrim strip

        # 1. Timeline Seek Slider
        self.timeline = TimelineSlider(self)
        self.timeline.seek_requested.connect(self.seek_requested.emit)
        self.main_layout.addWidget(self.timeline)

        # 2. Modular Buttons Row
        self.btn_row = QHBoxLayout()
        self.btn_row.setContentsMargins(0, 0, 0, 0)
        self.btn_row.setSpacing(8)

        # Left and right zones live in widgets forced to the same width, so the
        # center zone (play button) is exactly centered however many buttons
        # each side holds. See _equalize_side_zones().
        self.left_zone = QWidget(self)
        self.left_box = QHBoxLayout(self.left_zone)
        self.left_box.setContentsMargins(0, 0, 0, 0)
        self.left_box.setSpacing(6)
        self.btn_row.addWidget(self.left_zone)

        self.btn_row.addStretch()

        self.center_box = QHBoxLayout()
        self.center_box.setSpacing(8)
        self.btn_row.addLayout(self.center_box)

        self.btn_row.addStretch()

        self.right_zone = QWidget(self)
        self.right_box = QHBoxLayout(self.right_zone)
        self.right_box.setContentsMargins(0, 0, 0, 0)
        self.right_box.setSpacing(6)
        self.btn_row.addWidget(self.right_zone)

        self.main_layout.addLayout(self.btn_row)

        self._rebuild_buttons()

    def _rebuild_buttons(self):
        for box in [self.left_box, self.center_box, self.right_box]:
            while box.count():
                item = box.takeAt(0)
                w = item.widget()
                if w:
                    w.deleteLater()

        # Left zone hugs the left edge, right zone hugs the right edge.
        for key in self.current_layout.get("left", []):
            w = self._create_widget_for_key(key)
            if w: self.left_box.addWidget(w)
        self.left_box.addStretch()

        for key in self.current_layout.get("center", []):
            w = self._create_widget_for_key(key)
            if w: self.center_box.addWidget(w)

        self.right_box.addStretch()
        for key in self.current_layout.get("right", []):
            w = self._create_widget_for_key(key)
            if w: self.right_box.addWidget(w)

        self._equalize_side_zones()

    def set_compact(self, compact: bool):
        """Narrow windows: keep only the center transport zone."""
        if compact == self._compact:
            return
        self._compact = compact
        self.left_zone.setVisible(not compact)
        self.right_zone.setVisible(not compact)

    def _equalize_side_zones(self):
        # Size hints are only right once QSS (min-width etc.) has been applied.
        for zone in (self.left_zone, self.right_zone):
            zone.setMinimumWidth(0)
            zone.setMaximumWidth(16777215)
            for child in zone.findChildren(QWidget):
                child.ensurePolished()
            zone.layout().activate()
        side = max(self.left_zone.sizeHint().width(), self.right_zone.sizeHint().width())
        self.left_zone.setFixedWidth(side)
        self.right_zone.setFixedWidth(side)

    ICON_COLOR = "#F2FBFF"

    def _plain_button(self, icon_name: str, tooltip: str, icon_px: int = 16, color: str = None) -> GlassButton:
        """Icon-only round button without a disc: a soft highlight fades in on hover / press."""
        btn = GlassButton(self, "plain", 40, icon_px)
        btn.setIcon(get_svg_icon(icon_name, size=icon_px, color=color))
        btn.setToolTip(tooltip)
        return btn

    def _disc_button(self, icon_name: str, tooltip: str, diameter: int, icon_px: int) -> GlassButton:
        """Clear glass disc (transport buttons)."""
        btn = GlassButton(self, "disc", diameter, icon_px)
        btn.setIcon(get_svg_icon(icon_name, size=icon_px, color=self.ICON_COLOR))
        btn.setToolTip(tooltip)
        return btn

    def _create_widget_for_key(self, key: str) -> QWidget:
        if key == "play_pause":
            self.btn_play = self._disc_button("play_glass", "재생 / 일시정지 (Space)", PLAY_DISC, PLAY_ICON)
            self._update_play_button_icon()
            self.btn_play.clicked.connect(self.play_pause_clicked.emit)
            return self.btn_play

        elif key == "prev_frame":
            btn = self._plain_button("prev_frame_glass", "1프레임 이전 (,)", 20, self.ICON_COLOR)
            btn.clicked.connect(self.prev_frame_clicked.emit)
            return btn

        elif key == "next_frame":
            btn = self._plain_button("next_frame_glass", "1프레임 다음 (.)", 20, self.ICON_COLOR)
            btn.clicked.connect(self.next_frame_clicked.emit)
            return btn

        elif key == "seek_backward":
            btn = self._disc_button("backward_glass", "5초 뒤로 (←)", SIDE_DISC, SIDE_ICON)
            btn.clicked.connect(lambda: self.seek_backward_clicked.emit(5.0))
            return btn

        elif key == "seek_forward":
            btn = self._disc_button("forward_glass", "5초 앞으로 (→)", SIDE_DISC, SIDE_ICON)
            btn.clicked.connect(lambda: self.seek_forward_clicked.emit(5.0))
            return btn

        elif key == "time_label":
            self.lbl_time = QLabel("00:00 / 00:00", self)
            self.lbl_time.setStyleSheet("margin: 0 4px;")
            self._update_time_display()
            return self.lbl_time

        elif key == "speed_button":
            self.btn_speed = GlassButton(self, "pill", 32, text_px=14, text_pad=14, accent_text=True, bold=True)
            self.btn_speed.setText("1.00x")
            self.btn_speed.setToolTip("정밀 배속 조절 (클릭 시 팝업)")
            self.btn_speed.clicked.connect(self.speed_button_clicked.emit)
            return self.btn_speed

        elif key == "screenshot":
            btn = self._plain_button("screenshot", "화면 캡처 (Ctrl + S)")
            btn.clicked.connect(self.screenshot_clicked.emit)
            return btn

        elif key == "subtitle":
            btn = self._plain_button("subtitle", "자막 토글 (C)")
            btn.clicked.connect(self.subtitle_clicked.emit)
            return btn

        elif key == "volume":
            self.btn_mute = self._plain_button("volume_high", "음소거 토글 (M) / 마우스를 올리면 볼륨 조절")
            self._update_volume_icon()
            self.btn_mute.clicked.connect(self.mute_clicked.emit)
            self.btn_mute.installEventFilter(self)
            return self.btn_mute

        elif key == "fullscreen":
            btn = self._plain_button("fullscreen", "전체화면 (F)")
            btn.clicked.connect(self.fullscreen_clicked.emit)
            return btn

        elif key == "settings":
            btn = self._plain_button("settings", "컨트롤러 버튼 배열 설정")
            btn.clicked.connect(self._open_settings_dialog)
            return btn

        return None

    def _open_settings_dialog(self):
        dlg = ControllerSettingsDialog(self.current_layout, self)
        dlg.layout_changed.connect(self._save_layout)
        dlg.exec()

    # --- Icon Updates ---

    def _update_play_button_icon(self):
        if hasattr(self, "btn_play"):
            icon_name = "pause_glass" if self._is_playing else "play_glass"
            self.btn_play.setIcon(get_svg_icon(icon_name, size=PLAY_ICON, color=self.ICON_COLOR))

    def _update_volume_icon(self):
        if hasattr(self, "btn_mute"):
            icon_name = "volume_mute" if self._is_muted else "volume_high"
            self.btn_mute.setIcon(get_svg_icon(icon_name, size=16))

    # --- External State Updates ---

    def set_playback_state(self, is_playing: bool):
        self._is_playing = is_playing
        self._update_play_button_icon()
        if is_playing:
            self.trigger_activity()
        else:
            self.autohide_timer.stop()
            self._fade_in()

    def set_speed_display(self, speed: float):
        if hasattr(self, "btn_speed"):
            self.btn_speed.setText(f"{speed:.2f}x")

    def set_duration(self, duration: float):
        self._duration = duration
        self.timeline.set_duration(duration)
        self._update_time_display()

    def set_time_pos(self, time_pos: float):
        self._time_pos = time_pos
        self.timeline.set_time_pos(time_pos)
        self._update_time_display()

    def set_volume_display(self, vol: float, is_muted: bool = False):
        self._is_muted = is_muted
        self._update_volume_icon()
        self.volume_popup.set_value(int(vol))

    def _update_time_display(self):
        if hasattr(self, "lbl_time"):
            cur_str = self._format_seconds(self._time_pos)
            dur_str = self._format_seconds(self._duration)
            self.lbl_time.setText(f"{cur_str} / {dur_str}")

    @staticmethod
    def _format_seconds(secs: float) -> str:
        s = int(max(0, secs))
        m, s = divmod(s, 60)
        h, m = divmod(m, 60)
        if h > 0:
            return f"{h:02d}:{m:02d}:{s:02d}"
        return f"{m:02d}:{s:02d}"

    # --- Fast Responsive Auto-Hide Animations ---

    def set_media_loaded(self, loaded: bool):
        """No media: controls stay hidden (nothing to control yet)."""
        self._has_media = loaded
        if not loaded:
            self.autohide_timer.stop()
            self.volume_popup.hide()
            self.hide()
        else:
            self.trigger_activity()

    def _mouse_over_controls(self) -> bool:
        pos = self.mapFromGlobal(QCursor.pos())
        return self.rect().contains(pos) and pos.y() >= self.height() - self.CONTROLS_HEIGHT

    def paintEvent(self, event):
        # Bottom scrim: transparent at the top edge, dark behind the controls.
        p = QPainter(self)
        g = QLinearGradient(0, 0, 0, self.height())
        g.setColorAt(0.0, QColor(0, 0, 0, 0))
        g.setColorAt(0.45, QColor(0, 0, 0, int(255 * 0.45)))
        g.setColorAt(1.0, QColor(0, 0, 0, int(255 * self.SCRIM_ALPHA)))
        p.fillRect(self.rect(), g)

    def showEvent(self, event):
        super().showEvent(event)
        self.visibility_changed.emit(True)

    def hideEvent(self, event):
        super().hideEvent(event)
        self.visibility_changed.emit(False)

    # Clicks on the empty scrim area belong to the video (drag, double-click,
    # context menu), so hand them over instead of swallowing them here.
    def _forward_mouse(self, event: QMouseEvent):
        t = self.forward_target
        if t is None:
            event.ignore()
            return
        local = t.mapFromGlobal(event.globalPosition().toPoint())
        ev = QMouseEvent(event.type(), local, event.globalPosition(), event.button(),
                         event.buttons(), event.modifiers())
        QApplication.sendEvent(t, ev)
        event.accept()

    def mousePressEvent(self, event):
        self._forward_mouse(event)

    def mouseMoveEvent(self, event):
        self._forward_mouse(event)

    def mouseReleaseEvent(self, event):
        self._forward_mouse(event)

    def mouseDoubleClickEvent(self, event):
        self._forward_mouse(event)

    def contextMenuEvent(self, event):
        t = self.forward_target
        if t is None:
            event.ignore()
            return
        local = t.mapFromGlobal(event.globalPos())
        QApplication.sendEvent(t, QContextMenuEvent(event.reason(), local, event.globalPos(), event.modifiers()))
        event.accept()

    def trigger_activity(self):
        if not self._has_media:
            return
        if not self.isVisible():
            self.show()
        self._fade_in()
        if self._is_playing:
            self.autohide_timer.start(2800)

    def _fade_in(self):
        if self.opacity_effect.opacity() < 1.0:
            self.raise_()
            self.fade_anim.stop()
            self.fade_anim.setStartValue(self.opacity_effect.opacity())
            self.fade_anim.setEndValue(1.0)
            self.fade_anim.start()

    def eventFilter(self, obj, event):
        if obj is getattr(self, "btn_mute", None):
            if event.type() == QEvent.Enter:
                self.volume_popup.open_above(self.btn_mute)
            elif event.type() == QEvent.Leave:
                self.volume_popup.schedule_close()
            elif event.type() == QEvent.Wheel:
                step = 5 if event.angleDelta().y() > 0 else -5
                self.volume_popup.slider.setValue(self.volume_popup.slider.value() + step)
                return True
        return super().eventFilter(obj, event)

    def _fade_out(self):
        if (self._mouse_over_controls() or self.volume_popup.isVisible()
                or (self.hold_visible and self.hold_visible())):
            self.autohide_timer.start(2800)
            return

        self.fade_anim.stop()
        self.fade_anim.setStartValue(self.opacity_effect.opacity())
        self.fade_anim.setEndValue(0.0)
        self.fade_anim.start()

    def _hide_after_fade(self):
        if self.opacity_effect.opacity() <= 0.01:
            self.volume_popup.hide()
            self.hide()

    def enterEvent(self, event):
        self.autohide_timer.stop()
        if self._has_media:
            self.show()
            self._fade_in()
        super().enterEvent(event)

    def leaveEvent(self, event):
        if self._is_playing:
            self.autohide_timer.start(2800)
        super().leaveEvent(event)
