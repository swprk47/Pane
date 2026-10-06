import json
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QSlider, QApplication
)
from PySide6.QtCore import Qt, Signal, QPoint, QPointF, QRectF, QSize, QTimer, QEvent
from PySide6.QtGui import QPainter
from core.settings import open_settings
from ui.icons import get_svg_icon
from ui.glass_button import GlassButton, paint_glass_panel
from ui.glass_slider import GlassSlider

DEFAULT_PRESETS = [1.0, 1.2, 1.25, 1.5, 2.0]
MAX_PRESETS = 6          # more chips than this stop being readable

POPUP_QSS = """
    QLabel {
        color: #FFFFFF;
        font-family: "Segoe UI Variable Text", "Segoe UI", sans-serif;
        background: transparent;
    }
"""


class PresetChip(GlassButton):
    """
    One speed preset (a glass pill; the active one is lit). Hovering it reveals a small x in its top-right
    corner that removes just this preset.
    """
    delete_requested = Signal(float)
    chosen = Signal(float)

    def __init__(self, speed: float, active: bool, parent=None):
        super().__init__(parent, "pill", 36, width=54, text_px=13)
        self.speed = speed
        self.setText(f"{speed:g}x")
        self.setActive(active)
        self._act = 1.0 if active else 0.0           # no fade-in for a freshly built chip
        self.setToolTip(f"{speed:g}x 배속 적용")
        self.clicked.connect(lambda: self.chosen.emit(self.speed))

        self.btn_x = GlassButton(self, "flat", 16, icon_px=8, radius=8, danger=True, base=(40, 40, 52, 242))
        self.btn_x.setIcon(get_svg_icon("close", size=8))
        self.btn_x.setToolTip(f"{speed:g}x 프리셋 삭제")
        self.btn_x.move(self.width() - 19, 3)
        self.btn_x.hide()
        self.btn_x.clicked.connect(lambda: self.delete_requested.emit(self.speed))
        self.btn_x.installEventFilter(self)

    def _sync_x(self):
        self.btn_x.setVisible(self.underMouse() or self.btn_x.underMouse())

    def enterEvent(self, event):
        super().enterEvent(event)
        self.btn_x.show()
        self.btn_x.raise_()

    def leaveEvent(self, event):
        super().leaveEvent(event)
        # Moving from the chip onto its own x must not hide it.
        QTimer.singleShot(0, self._sync_x)

    def eventFilter(self, obj, event):
        if obj is self.btn_x and event.type() == event.Type.Leave:
            QTimer.singleShot(0, self._sync_x)
        return super().eventFilter(obj, event)


class SpeedPopup(QWidget):
    """
    Speed panel: pinned preset chips (max 6, each removable via a hover x),
    a 0.05x precision slider and a pin toggle for the current speed.
    """
    speed_selected = Signal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("SpeedPopupWidget")
        # A child widget of the main window (like the volume popup). A separate
        # translucent Qt.Popup window rendered garbled here (video showing
        # through, stale chips), so the panel lives inside the window instead.
        # Without WA_StyledBackground a plain QWidget ignores the QSS background.
        self.setFixedWidth(396)
        self._anchor = None
        self.hide()

        self.settings = open_settings("SpeedSettings")
        self._current_speed = 1.0
        self.presets = self._load_presets()

        self._init_ui()

    def paintEvent(self, event):
        p = QPainter(self)
        paint_glass_panel(p, QRectF(self.rect()), 18)

    # --- persistence ------------------------------------------------------

    def _load_presets(self) -> list:
        raw = self.settings.value("custom_presets", None)
        if raw:
            try:
                presets = json.loads(raw)
                if isinstance(presets, list) and presets:
                    cleaned = sorted(set(round(float(p), 2) for p in presets))
                    return cleaned[:MAX_PRESETS]
            except Exception:
                pass
        return list(DEFAULT_PRESETS)

    def _save_presets(self):
        self.settings.setValue("custom_presets", json.dumps(self.presets))

    # --- UI ---------------------------------------------------------------

    def _init_ui(self):
        self.setStyleSheet(POPUP_QSS)

        main = QVBoxLayout(self)
        main.setContentsMargins(18, 16, 18, 16)
        main.setSpacing(14)

        # Header: title, current speed, reset
        header = QHBoxLayout()
        header.setSpacing(10)
        title = QLabel("재생 속도", self)
        title.setStyleSheet("font-size: 13px; font-weight: 600; color: rgba(255, 255, 255, 0.78);")
        header.addWidget(title)

        self.lbl_speed_val = QLabel("1.00x", self)
        self.lbl_speed_val.setStyleSheet(f"font-size: 20px; font-weight: 700; color: #FFFFFF;")
        header.addWidget(self.lbl_speed_val)
        header.addStretch()

        self.btn_reset = GlassButton(self, "pill", 26, text_px=12, text_pad=12)
        self.btn_reset.setText("기본값")
        self.btn_reset.setToolTip("프리셋을 기본 구성으로 되돌리기")
        self.btn_reset.clicked.connect(self._reset_to_default_presets)
        header.addWidget(self.btn_reset)
        main.addLayout(header)

        # Preset chips
        self.preset_container = QWidget(self)
        self.preset_layout = QHBoxLayout(self.preset_container)
        self.preset_layout.setContentsMargins(0, 0, 0, 0)
        self.preset_layout.setSpacing(6)
        self.preset_container.setFixedHeight(36)
        main.addWidget(self.preset_container)

        # Slider row: 0.25x .. 3.00x in 0.05x steps (25..300, step 5)
        slider_row = QHBoxLayout()
        slider_row.setSpacing(12)
        self.slider = GlassSlider(Qt.Horizontal, self, snap_step=5)
        self.slider.setRange(25, 300)
        self.slider.setSingleStep(5)
        self.slider.setPageStep(10)
        self.slider.setValue(100)
        self.slider.setFixedHeight(26)
        self.slider.valueChanged.connect(self._on_slider_value_changed)
        slider_row.addWidget(self.slider, stretch=1)

        self.btn_pin = GlassButton(self, "disc", 34, icon_px=16, shadow=False)
        self.btn_pin.clicked.connect(self._on_pin_clicked)
        slider_row.addWidget(self.btn_pin)

        self.lbl_count = QLabel("", self)
        self.lbl_count.setFixedWidth(30)
        self.lbl_count.setAlignment(Qt.AlignCenter)
        self.lbl_count.setStyleSheet("font-size: 12px; font-weight: 600; color: rgba(255, 255, 255, 0.55);")
        slider_row.addWidget(self.lbl_count)
        main.addLayout(slider_row)

        # Status line (hints / "max reached")
        self.lbl_hint = QLabel("", self)
        self.lbl_hint.setAlignment(Qt.AlignCenter)
        self.lbl_hint.setStyleSheet("font-size: 11px; color: rgba(255, 255, 255, 0.48);")
        main.addWidget(self.lbl_hint)

        self._hint_timer = QTimer(self)
        self._hint_timer.setSingleShot(True)
        self._hint_timer.setInterval(2200)
        self._hint_timer.timeout.connect(self._reset_hint)

        self._rebuild_preset_buttons()
        self._refresh_pin_state()
        self._reset_hint()

    def _reset_hint(self):
        self.lbl_hint.setStyleSheet("font-size: 11px; color: rgba(255, 255, 255, 0.48);")
        self.lbl_hint.setText("칩에 마우스를 올리면 ✕로 삭제 · 핀으로 현재 배속 추가")

    def _flash_hint(self, text: str):
        self.lbl_hint.setStyleSheet("font-size: 11px; font-weight: 600; color: #FFB340;")
        self.lbl_hint.setText(text)
        self._hint_timer.start()

    def _rebuild_preset_buttons(self):
        while self.preset_layout.count():
            item = self.preset_layout.takeAt(0)
            widget = item.widget()
            if widget:
                # deleteLater() alone leaves the old chip painted until the next
                # event-loop turn (visible as ghost text on top of the new one).
                widget.hide()
                widget.setParent(None)
                widget.deleteLater()

        for spd in sorted(self.presets):
            active = abs(spd - self._current_speed) < 0.01
            chip = PresetChip(spd, active, self.preset_container)
            chip.chosen.connect(self._apply_speed)
            chip.delete_requested.connect(self._unpin_preset)
            self.preset_layout.addWidget(chip)
        self.preset_layout.addStretch()
        self._refresh_pin_state()

    def _is_pinned(self, value: float) -> bool:
        return any(abs(value - p) < 0.001 for p in self.presets)

    def _refresh_pin_state(self):
        full = len(self.presets) >= MAX_PRESETS
        pinned = self._is_pinned(self._current_speed)
        if pinned:
            self.btn_pin.setIcon(get_svg_icon("pin_fill", size=16, color="#FFFFFF"))
            self.btn_pin.setToolTip("고정 해제 (프리셋에서 제거)")
        elif full:
            self.btn_pin.setIcon(get_svg_icon("pin", size=16, color="#7A7F8C"))
            self.btn_pin.setToolTip(f"프리셋은 최대 {MAX_PRESETS}개입니다. 먼저 하나를 삭제하세요")
        else:
            self.btn_pin.setIcon(get_svg_icon("pin", size=16))
            self.btn_pin.setToolTip("현재 배속을 프리셋에 고정")
        self.lbl_count.setText(f"{len(self.presets)}/{MAX_PRESETS}")

    # --- preset editing ---------------------------------------------------

    def _on_pin_clicked(self):
        value = round(self.slider.value() / 100.0, 2)
        if self._is_pinned(value):
            self._unpin_preset(self._match_preset(value))
        elif not self._pin_current_speed():
            self._flash_hint(f"프리셋은 최대 {MAX_PRESETS}개까지 — ✕로 하나 삭제한 뒤 추가하세요")

    def _match_preset(self, value: float) -> float:
        return next(p for p in self.presets if abs(value - p) < 0.001)

    def _pin_current_speed(self) -> bool:
        """Pin the slider's speed. False when the preset list is already full."""
        val = round(self.slider.value() / 100.0, 2)
        if self._is_pinned(val):
            return True
        if len(self.presets) >= MAX_PRESETS:
            return False
        self.presets.append(val)
        self.presets.sort()
        self._save_presets()
        self._rebuild_preset_buttons()
        return True

    def _unpin_preset(self, speed: float):
        if speed in self.presets:
            self.presets.remove(speed)
            self._save_presets()
            self._rebuild_preset_buttons()

    def _reset_to_default_presets(self):
        self.presets = list(DEFAULT_PRESETS)
        self._save_presets()
        self._rebuild_preset_buttons()

    # --- speed ------------------------------------------------------------

    def _on_slider_value_changed(self, raw_val: int):
        snapped = round(raw_val / 5.0) * 5  # snap to 0.05 steps
        spd = round(snapped / 100.0, 2)
        self.lbl_speed_val.setText(f"{spd:.2f}x")
        previous = self._current_speed
        self._current_speed = spd
        self.speed_selected.emit(spd)
        # Chips only change look when the active preset changes.
        if self._is_pinned(previous) or self._is_pinned(spd):
            self._rebuild_preset_buttons()
        else:
            self._refresh_pin_state()

    def _apply_speed(self, speed: float):
        self.set_current_speed(speed)
        self.speed_selected.emit(speed)

    def set_current_speed(self, speed: float):
        """Update current speed from external engine changes."""
        self._current_speed = round(speed, 2)
        self.lbl_speed_val.setText(f"{self._current_speed:.2f}x")

        self.slider.blockSignals(True)
        self.slider.setValue(int(round(self._current_speed * 100)))
        self.slider.blockSignals(False)

        self._rebuild_preset_buttons()

    # --- showing / dismissing --------------------------------------------

    def show_above_widget(self, target_widget: QWidget):
        """Float the panel above `target_widget`, kept inside the parent window."""
        self._anchor = target_widget
        self.adjustSize()
        parent = self.parentWidget()
        pos = target_widget.mapTo(parent, QPoint(0, 0))
        x = pos.x() + (target_widget.width() - self.width()) // 2
        y = pos.y() - self.height() - 10
        x = max(8, min(x, parent.width() - self.width() - 8))
        y = max(8, y)
        self.move(x, y)
        self.show()
        self.raise_()

    def toggle_above_widget(self, target_widget: QWidget):
        if self.isVisible():
            self.hide()
        else:
            self.show_above_widget(target_widget)

    def showEvent(self, event):
        super().showEvent(event)
        QApplication.instance().installEventFilter(self)

    def hideEvent(self, event):
        super().hideEvent(event)
        QApplication.instance().removeEventFilter(self)

    def eventFilter(self, obj, event):
        # Click outside the panel (and not on its own button) dismisses it.
        if self.isVisible() and event.type() == QEvent.MouseButtonPress:
            g = event.globalPosition().toPoint()
            inside = self.rect().contains(self.mapFromGlobal(g))
            on_anchor = (self._anchor is not None and
                         self._anchor.rect().contains(self._anchor.mapFromGlobal(g)))
            if not inside and not on_anchor:
                self.hide()
        return super().eventFilter(obj, event)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.hide()
        else:
            super().keyPressEvent(event)
