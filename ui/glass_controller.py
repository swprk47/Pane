import json
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QSlider, QDialog, QListWidget,
    QListWidgetItem, QGraphicsOpacityEffect
)
from PySide6.QtCore import Qt, Signal, QTimer, QPropertyAnimation, QEasingCurve, QSettings, QSize
from ui.timeline_slider import TimelineSlider
from ui.icons import get_svg_icon

DEFAULT_LAYOUT = {
    "left": ["play_pause", "prev_frame", "next_frame", "time_label"],
    "center": ["seek_backward", "speed_button", "seek_forward"],
    "right": ["screenshot", "subtitle", "volume", "fullscreen", "settings"]
}

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
                background-color: rgba(10, 132, 255, 0.45);
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
        btn_save.setStyleSheet("background: #0A84FF; border: none; font-weight: bold;")
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

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("GlassControllerCapsule")
        self.setFixedHeight(84)
        self.setMinimumWidth(580)

        self.settings = QSettings("GlassPlayer", "ControllerLayout")
        self.current_layout = self._load_layout()

        self._is_playing = False
        self._is_muted = False
        self._duration = 0.0
        self._time_pos = 0.0

        self._init_ui()

        # Fast 120ms animation for instant responsiveness
        self.opacity_effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self.opacity_effect)
        self.opacity_effect.setOpacity(1.0)

        self.fade_anim = QPropertyAnimation(self.opacity_effect, b"opacity")
        self.fade_anim.setDuration(120)
        self.fade_anim.setEasingCurve(QEasingCurve.OutQuad)
        self.fade_anim.finished.connect(self._hide_after_fade)

        self.autohide_timer = QTimer(self)
        self.autohide_timer.setInterval(2800)
        self.autohide_timer.setSingleShot(True)
        self.autohide_timer.timeout.connect(self._fade_out)

    def _load_layout(self) -> dict:
        raw = self.settings.value("button_layout", None)
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
            QWidget#GlassControllerCapsule {
                background-color: rgba(22, 22, 30, 0.92);
                border: 1px solid rgba(255, 255, 255, 0.22);
                border-radius: 24px;
            }
            QPushButton {
                background: transparent;
                border: 1px solid transparent;
                color: #FFFFFF;
                border-radius: 8px;
                padding: 6px;
                min-width: 34px;
                min-height: 34px;
                outline: none;
                qproperty-cursor: PointingHandCursor;
            }
            QPushButton:hover {
                background: rgba(255, 255, 255, 0.20);
                border: 1px solid rgba(255, 255, 255, 0.30);
                color: #FFFFFF;
            }
            QPushButton:pressed {
                background: rgba(10, 132, 255, 0.55);
                border: 1px solid rgba(112, 180, 255, 0.95);
                padding-top: 7px;
                padding-bottom: 5px;
            }
            QPushButton:focus {
                border: 1px solid rgba(112, 180, 255, 0.80);
            }
            QLabel {
                color: rgba(255, 255, 255, 0.85);
                font-family: "Segoe UI Variable Text", "Segoe UI", sans-serif;
                font-size: 12px;
            }
            QSlider::groove:horizontal {
                height: 4px;
                background: rgba(255, 255, 255, 0.22);
                border-radius: 2px;
            }
            QSlider::sub-page:horizontal {
                background: #0A84FF;
                border-radius: 2px;
            }
            QSlider::handle:horizontal {
                background: #FFFFFF;
                width: 12px;
                margin-top: -4px;
                margin-bottom: -4px;
                border-radius: 6px;
            }
            QSlider::handle:horizontal:hover {
                background: #70B4FF;
                width: 14px;
                margin-top: -5px;
                margin-bottom: -5px;
            }
            QSlider::handle:horizontal:pressed {
                background: #0A84FF;
                border: 2px solid #FFFFFF;
                width: 14px;
                margin-top: -5px;
                margin-bottom: -5px;
            }
        """)

        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(18, 8, 18, 10)
        self.main_layout.setSpacing(6)

        # 1. Timeline Seek Slider
        self.timeline = TimelineSlider(self)
        self.timeline.seek_requested.connect(self.seek_requested.emit)
        self.main_layout.addWidget(self.timeline)

        # 2. Modular Buttons Row
        self.btn_row = QHBoxLayout()
        self.btn_row.setContentsMargins(0, 0, 0, 0)
        self.btn_row.setSpacing(8)

        self.left_box = QHBoxLayout()
        self.left_box.setSpacing(6)
        self.btn_row.addLayout(self.left_box)

        self.btn_row.addStretch()

        self.center_box = QHBoxLayout()
        self.center_box.setSpacing(8)
        self.btn_row.addLayout(self.center_box)

        self.btn_row.addStretch()

        self.right_box = QHBoxLayout()
        self.right_box.setSpacing(6)
        self.btn_row.addLayout(self.right_box)

        self.main_layout.addLayout(self.btn_row)

        self._rebuild_buttons()

    def _rebuild_buttons(self):
        for box in [self.left_box, self.center_box, self.right_box]:
            while box.count():
                item = box.takeAt(0)
                w = item.widget()
                if w:
                    w.deleteLater()

        for key in self.current_layout.get("left", []):
            w = self._create_widget_for_key(key)
            if w: self.left_box.addWidget(w)

        for key in self.current_layout.get("center", []):
            w = self._create_widget_for_key(key)
            if w: self.center_box.addWidget(w)

        for key in self.current_layout.get("right", []):
            w = self._create_widget_for_key(key)
            if w: self.right_box.addWidget(w)

    def _create_widget_for_key(self, key: str) -> QWidget:
        if key == "play_pause":
            self.btn_play = QPushButton(self)
            self._update_play_button_icon()
            self.btn_play.setIconSize(QSize(18, 18))
            self.btn_play.setToolTip("재생 / 일시정지 (Space)")
            self.btn_play.clicked.connect(self.play_pause_clicked.emit)
            return self.btn_play

        elif key == "prev_frame":
            btn = QPushButton(self)
            btn.setIcon(get_svg_icon("prev_frame", size=16))
            btn.setIconSize(QSize(16, 16))
            btn.setToolTip("1프레임 이전 (,)")
            btn.clicked.connect(self.prev_frame_clicked.emit)
            return btn

        elif key == "next_frame":
            btn = QPushButton(self)
            btn.setIcon(get_svg_icon("next_frame", size=16))
            btn.setIconSize(QSize(16, 16))
            btn.setToolTip("1프레임 다음 (.)")
            btn.clicked.connect(self.next_frame_clicked.emit)
            return btn

        elif key == "seek_backward":
            btn = QPushButton(self)
            btn.setIcon(get_svg_icon("backward_5", size=18))
            btn.setIconSize(QSize(18, 18))
            btn.setToolTip("5초 뒤로 (←)")
            btn.clicked.connect(lambda: self.seek_backward_clicked.emit(5.0))
            return btn

        elif key == "seek_forward":
            btn = QPushButton(self)
            btn.setIcon(get_svg_icon("forward_5", size=18))
            btn.setIconSize(QSize(18, 18))
            btn.setToolTip("5초 앞으로 (→)")
            btn.clicked.connect(lambda: self.seek_forward_clicked.emit(5.0))
            return btn

        elif key == "time_label":
            self.lbl_time = QLabel("00:00 / 00:00", self)
            self.lbl_time.setStyleSheet("color: rgba(255, 255, 255, 0.75); font-size: 12px; margin: 0 4px;")
            self._update_time_display()
            return self.lbl_time

        elif key == "speed_button":
            self.btn_speed = QPushButton("1.00x", self)
            self.btn_speed.setObjectName("SpeedButton")
            self.btn_speed.setToolTip("정밀 배속 조절 (클릭 시 팝업)")
            self.btn_speed.setStyleSheet("""
                QPushButton#SpeedButton {
                    background: rgba(10, 132, 255, 0.22);
                    border: 1px solid rgba(10, 132, 255, 0.45);
                    border-radius: 8px;
                    color: #70B4FF;
                    font-size: 13px;
                    font-weight: 700;
                    padding: 3px 10px;
                }
                QPushButton#SpeedButton:hover {
                    background: rgba(10, 132, 255, 0.40);
                    border: 1px solid rgba(112, 180, 255, 0.95);
                    color: #FFFFFF;
                }
                QPushButton#SpeedButton:pressed {
                    background: rgba(10, 132, 255, 0.70);
                    border: 1px solid #70B4FF;
                    color: #FFFFFF;
                    padding-top: 4px;
                    padding-bottom: 2px;
                }
            """)
            self.btn_speed.clicked.connect(self.speed_button_clicked.emit)
            return self.btn_speed

        elif key == "screenshot":
            btn = QPushButton(self)
            btn.setIcon(get_svg_icon("screenshot", size=16))
            btn.setIconSize(QSize(16, 16))
            btn.setToolTip("화면 캡처 (Ctrl + S)")
            btn.clicked.connect(self.screenshot_clicked.emit)
            return btn

        elif key == "subtitle":
            btn = QPushButton(self)
            btn.setIcon(get_svg_icon("subtitle", size=16))
            btn.setIconSize(QSize(16, 16))
            btn.setToolTip("자막 토글 (C)")
            btn.clicked.connect(self.subtitle_clicked.emit)
            return btn

        elif key == "volume":
            vol_widget = QWidget(self)
            vl = QHBoxLayout(vol_widget)
            vl.setContentsMargins(0, 0, 0, 0)
            vl.setSpacing(4)

            self.btn_mute = QPushButton(self)
            self._update_volume_icon()
            self.btn_mute.setIconSize(QSize(16, 16))
            self.btn_mute.setToolTip("음소거 토글 (M)")
            self.btn_mute.clicked.connect(self.mute_clicked.emit)
            vl.addWidget(self.btn_mute)

            self.vol_slider = QSlider(Qt.Horizontal, self)
            self.vol_slider.setRange(0, 100)
            self.vol_slider.setValue(100)
            self.vol_slider.setFixedWidth(70)
            self.vol_slider.valueChanged.connect(lambda v: self.volume_changed.emit(float(v)))
            vl.addWidget(self.vol_slider)
            return vol_widget

        elif key == "fullscreen":
            btn = QPushButton(self)
            btn.setIcon(get_svg_icon("fullscreen", size=16))
            btn.setIconSize(QSize(16, 16))
            btn.setToolTip("전체화면 (F)")
            btn.clicked.connect(self.fullscreen_clicked.emit)
            return btn

        elif key == "settings":
            btn = QPushButton(self)
            btn.setIcon(get_svg_icon("settings", size=16))
            btn.setIconSize(QSize(16, 16))
            btn.setToolTip("컨트롤러 버튼 배열 설정")
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
            icon_name = "pause" if self._is_playing else "play"
            self.btn_play.setIcon(get_svg_icon(icon_name, size=18))

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
        if hasattr(self, "vol_slider"):
            self.vol_slider.blockSignals(True)
            self.vol_slider.setValue(int(vol))
            self.vol_slider.blockSignals(False)

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

    def trigger_activity(self):
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

    def _fade_out(self):
        if self.underMouse():
            self.autohide_timer.start(2800)
            return

        self.fade_anim.stop()
        self.fade_anim.setStartValue(self.opacity_effect.opacity())
        self.fade_anim.setEndValue(0.0)
        self.fade_anim.start()

    def _hide_after_fade(self):
        if self.opacity_effect.opacity() <= 0.01:
            self.hide()

    def enterEvent(self, event):
        self.autohide_timer.stop()
        self.show()
        self._fade_in()
        super().enterEvent(event)

    def leaveEvent(self, event):
        if self._is_playing:
            self.autohide_timer.start(2800)
        super().leaveEvent(event)
