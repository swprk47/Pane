import json
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QSlider, QMenu, QGraphicsDropShadowEffect
)
from PySide6.QtCore import Qt, Signal, QSettings, QPoint
from PySide6.QtGui import QColor, QAction
from core.settings import open_settings

DEFAULT_PRESETS = [1.0, 1.2, 1.25, 1.5, 2.0]


class SpeedPopup(QWidget):
    """
    Apple Glass Speed Adjustment Popup with Custom Pin/Unpin Presets and 0.05x Precision Slider.
    """
    speed_selected = Signal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("SpeedPopupWidget")
        self.setWindowFlags(Qt.Popup | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setFixedWidth(280)

        self.settings = open_settings("SpeedSettings")
        self._current_speed = 1.0
        self.presets = self._load_presets()

        self._init_ui()

    def _load_presets(self) -> list:
        raw = self.settings.value("custom_presets", None)
        if raw:
            try:
                presets = json.loads(raw)
                if isinstance(presets, list) and presets:
                    return sorted(list(set(float(p) for p in presets)))
            except Exception:
                pass
        return list(DEFAULT_PRESETS)

    def _save_presets(self):
        self.settings.setValue("custom_presets", json.dumps(self.presets))

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(14, 14, 14, 14)
        main_layout.setSpacing(12)

        # Style for popup container
        self.setStyleSheet("""
            QWidget#SpeedPopupWidget {
                background-color: rgba(28, 28, 36, 0.94);
                border: 1px solid rgba(255, 255, 255, 0.20);
                border-radius: 16px;
            }
            QLabel {
                color: #FFFFFF;
                font-family: "Segoe UI Variable Text", "Segoe UI", sans-serif;
            }
            QSlider::groove:horizontal {
                height: 6px;
                background: rgba(255, 255, 255, 0.15);
                border-radius: 3px;
            }
            QSlider::sub-page:horizontal {
                background: #0A84FF;
                border-radius: 3px;
            }
            QSlider::handle:horizontal {
                background: #FFFFFF;
                width: 18px;
                margin-top: -6px;
                margin-bottom: -6px;
                border-radius: 9px;
                border: 1px solid rgba(0, 0, 0, 0.2);
            }
            QSlider::handle:horizontal:hover {
                background: #F0F0F5;
                transform: scale(1.1);
            }
        """)

        # Soft shadow
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(25)
        shadow.setColor(QColor(0, 0, 0, 180))
        shadow.setOffset(0, 6)
        self.setGraphicsEffect(shadow)

        # 1. Header (Title & Reset)
        header_layout = QHBoxLayout()
        title_label = QLabel("재생 속도 설정", self)
        title_label.setStyleSheet("font-size: 13px; font-weight: 600; color: rgba(255, 255, 255, 0.9);")
        header_layout.addWidget(title_label)

        header_layout.addStretch()

        self.btn_reset = QPushButton("기본값", self)
        self.btn_reset.setToolTip("기본 프리셋으로 초기화")
        self.btn_reset.setStyleSheet("""
            QPushButton {
                background: transparent;
                border: none;
                color: rgba(255, 255, 255, 0.45);
                font-size: 11px;
                padding: 2px 4px;
            }
            QPushButton:hover {
                color: #FF453A;
            }
        """)
        self.btn_reset.clicked.connect(self._reset_to_default_presets)
        header_layout.addWidget(self.btn_reset)
        main_layout.addLayout(header_layout)

        # 2. Preset Chips Area
        self.preset_container = QWidget(self)
        self.preset_layout = QHBoxLayout(self.preset_container)
        self.preset_layout.setContentsMargins(0, 0, 0, 0)
        self.preset_layout.setSpacing(6)
        main_layout.addWidget(self.preset_container)
        self._rebuild_preset_buttons()

        # 3. Precision Slider Row
        slider_row = QHBoxLayout()
        self.lbl_speed_val = QLabel("1.00x", self)
        self.lbl_speed_val.setStyleSheet("font-size: 14px; font-weight: bold; color: #0A84FF; min-width: 48px;")
        slider_row.addWidget(self.lbl_speed_val)

        # 0.25x to 3.00x with 0.05 step -> integer range 25 to 300, step 5
        self.slider = QSlider(Qt.Horizontal, self)
        self.slider.setRange(25, 300)
        self.slider.setSingleStep(5)
        self.slider.setPageStep(10)
        self.slider.setValue(100)
        self.slider.valueChanged.connect(self._on_slider_value_changed)
        slider_row.addWidget(self.slider, stretch=1)

        # Pin button (📌) to pin current slider speed to presets
        self.btn_pin = QPushButton("📌", self)
        self.btn_pin.setToolTip("현재 배속을 프리셋에 고정 추가")
        self.btn_pin.setStyleSheet("""
            QPushButton {
                background: rgba(255, 255, 255, 0.10);
                border: 1px solid rgba(255, 255, 255, 0.18);
                border-radius: 8px;
                color: #FFFFFF;
                font-size: 13px;
                min-width: 28px;
                min-height: 28px;
                max-width: 28px;
                max-height: 28px;
            }
            QPushButton:hover {
                background: rgba(10, 132, 255, 0.4);
                border: 1px solid #0A84FF;
            }
        """)
        self.btn_pin.clicked.connect(self._pin_current_speed)
        slider_row.addWidget(self.btn_pin)

        main_layout.addLayout(slider_row)

        # Subtitle tip for unpinning
        tip_label = QLabel("Tip: 프리셋 버튼 우클릭 시 삭제 가능", self)
        tip_label.setStyleSheet("font-size: 10px; color: rgba(255, 255, 255, 0.35); margin-top: -4px;")
        tip_label.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(tip_label)

    def _rebuild_preset_buttons(self):
        # Clear existing buttons
        while self.preset_layout.count():
            item = self.preset_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        # Create chip for each preset
        for spd in sorted(self.presets):
            btn = QPushButton(f"{spd:g}x", self)
            btn.setToolTip(f"{spd:g}x 배속 적용 (우클릭하여 프리셋 삭제)")
            btn.setContextMenuPolicy(Qt.CustomContextMenu)
            btn.customContextMenuRequested.connect(lambda pos, s=spd: self._show_preset_context_menu(pos, s))

            is_active = (abs(spd - self._current_speed) < 0.01)
            btn_style = f"""
                QPushButton {{
                    background: {'rgba(10, 132, 255, 0.5)' if is_active else 'rgba(255, 255, 255, 0.08)'};
                    border: 1px solid {'#0A84FF' if is_active else 'rgba(255, 255, 255, 0.12)'};
                    border-radius: 8px;
                    color: #FFFFFF;
                    font-size: 12px;
                    font-weight: 500;
                    padding: 5px 8px;
                }}
                QPushButton:hover {{
                    background: rgba(255, 255, 255, 0.22);
                    border: 1px solid rgba(255, 255, 255, 0.3);
                }}
            """
            btn.setStyleSheet(btn_style)
            btn.clicked.connect(lambda _, s=spd: self._apply_speed(s))
            self.preset_layout.addWidget(btn)

    def _show_preset_context_menu(self, pos: QPoint, speed: float):
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background-color: rgba(35, 35, 45, 0.95);
                border: 1px solid rgba(255, 255, 255, 0.2);
                border-radius: 8px;
                padding: 4px;
            }
            QMenu::item {
                color: #FFFFFF;
                padding: 4px 12px;
                border-radius: 4px;
            }
            QMenu::item:selected {
                background-color: #E81123;
            }
        """)
        act_delete = QAction(f"✕ {speed:g}x 프리셋 삭제", self)
        act_delete.triggered.connect(lambda: self._unpin_preset(speed))
        menu.addAction(act_delete)
        menu.exec(self.sender().mapToGlobal(pos))

    def _pin_current_speed(self):
        val = round(self.slider.value() / 100.0, 2)
        if val not in self.presets:
            self.presets.append(val)
            self.presets.sort()
            self._save_presets()
            self._rebuild_preset_buttons()

    def _unpin_preset(self, speed: float):
        if speed in self.presets:
            self.presets.remove(speed)
            self._save_presets()
            self._rebuild_preset_buttons()

    def _reset_to_default_presets(self):
        self.presets = list(DEFAULT_PRESETS)
        self._save_presets()
        self._rebuild_preset_buttons()

    def _on_slider_value_changed(self, raw_val: int):
        # Snap to 0.05 step
        snapped = round(raw_val / 5.0) * 5
        spd = round(snapped / 100.0, 2)
        self.lbl_speed_val.setText(f"{spd:.2f}x")
        self._current_speed = spd
        self.speed_selected.emit(spd)
        self._rebuild_preset_buttons()

    def _apply_speed(self, speed: float):
        self.set_current_speed(speed)
        self.speed_selected.emit(speed)

    def set_current_speed(self, speed: float):
        """Update current speed from external engine changes."""
        self._current_speed = round(speed, 2)
        self.lbl_speed_val.setText(f"{self._current_speed:.2f}x")

        # Block signals briefly to prevent loop
        self.slider.blockSignals(True)
        int_val = int(round(self._current_speed * 100))
        self.slider.setValue(int_val)
        self.slider.blockSignals(False)

        self._rebuild_preset_buttons()

    def show_above_widget(self, target_widget: QWidget):
        """Position and show popup floating right above the target button."""
        self.adjustSize()
        global_target = target_widget.mapToGlobal(QPoint(0, 0))
        x = global_target.x() + (target_widget.width() - self.width()) // 2
        y = global_target.y() - self.height() - 8
        self.move(x, y)
        self.show()
