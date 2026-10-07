import json
import math
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QApplication, QLineEdit, QStackedLayout
)
from PySide6.QtCore import Qt, Signal, QPoint, QRectF, QTimer, QEvent
from PySide6.QtGui import QPainter
from core.settings import open_settings
from ui.icons import get_svg_icon
from ui.glass_button import GlassButton, paint_glass_panel
from ui.glass_slider import GlassSlider

DEFAULT_PRESETS = [1.0, 1.2, 1.25, 1.5, 2.0]
MAX_PRESETS = 6          # more rows than this stop being readable

MIN_SPEED, MAX_SPEED = 0.25, 3.0    # what the slider (and so a typed value) can reach
SPEED_STEP = 0.05

PANEL_WIDTH = 190
PAD_X, PAD_TOP, PAD_BOTTOM = 12, 10, 12
ROW_HEIGHT = 24
ROW_WIDTH = PANEL_WIDTH - 2 * PAD_X
VALUE_WIDTH = 40         # the current speed ("1.50x") left of the slider, also where the typing box opens
FLASH_COLOR = "#FFB340"

POPUP_QSS = """
    QLabel {
        color: #FFFFFF;
        font-family: "Segoe UI Variable Text", "Segoe UI", sans-serif;
        background: transparent;
    }
"""

COUNT_QSS = "font-size: 11px; font-weight: 600; color: rgba(255, 255, 255, 0.45);"
COUNT_FLASH_QSS = f"font-size: 11px; font-weight: 700; color: {FLASH_COLOR};"
VALUE_QSS = "font-size: 14px; font-weight: 700; color: #FFFFFF;"
VALUE_HOVER_QSS = VALUE_QSS + " text-decoration: underline;"
EDIT_QSS = (
    "QLineEdit { background: rgba(255, 255, 255, 0.14); border: 1px solid rgba(255, 255, 255, 0.55);"
    " border-radius: 6px; color: #FFFFFF; font-family: 'Segoe UI Variable Text', 'Segoe UI', sans-serif;"
    " font-size: 13px; font-weight: 700; padding: 0 3px; selection-background-color: rgba(255, 255, 255, 0.35); }"
)


def parse_speed_input(text: str):
    """What the user typed in the speed box -> a speed on the 0.05 grid inside the slider's range, or None."""
    t = text.strip().lower().replace(",", ".")
    if t.endswith("x"):
        t = t[:-1].strip()
    try:
        value = float(t)
    except ValueError:
        return None
    if not math.isfinite(value):
        return None
    value = max(MIN_SPEED, min(MAX_SPEED, value))
    return round(round(value / SPEED_STEP) * SPEED_STEP, 2)


class PresetChip(GlassButton):
    """
    One speed preset (a glass pill row; the active one is lit). Hovering it reveals a small x at its right
    end that removes just this preset.
    """
    delete_requested = Signal(float)
    chosen = Signal(float)

    def __init__(self, speed: float, active: bool, parent=None):
        super().__init__(parent, "pill", ROW_HEIGHT, width=ROW_WIDTH, text_px=12, text_pad=12,
                         bold=active, align_left=True, calm=True)
        self.speed = speed
        self.setText(f"{speed:g}x")
        self.setActive(active)
        self._act = 1.0 if active else 0.0           # no fade-in for a freshly built chip
        self.setToolTip(f"{speed:g}x 배속 적용")
        self.clicked.connect(lambda: self.chosen.emit(self.speed))

        self.btn_x = GlassButton(self, "flat", 16, icon_px=7, radius=8, danger=True, base=(40, 40, 52, 242))
        self.btn_x.setIcon(get_svg_icon("close", size=7))
        self.btn_x.setToolTip(f"{speed:g}x 프리셋 삭제")
        self.btn_x.move(self.width() - 20, (ROW_HEIGHT - 16) // 2)
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


class _SpeedValueLabel(QLabel):
    """The current speed as text; a click opens the typing box."""
    clicked = Signal()

    def __init__(self, parent=None):
        super().__init__("1.00x", parent)
        self.setStyleSheet(VALUE_QSS)
        self.setCursor(Qt.IBeamCursor)
        self.setToolTip("클릭해서 배속 직접 입력")

    def enterEvent(self, event):
        self.setStyleSheet(VALUE_HOVER_QSS)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.setStyleSheet(VALUE_QSS)
        super().leaveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self.rect().contains(event.position().toPoint()):
            self.clicked.emit()
            event.accept()
        else:
            super().mouseReleaseEvent(event)


class _SpeedEdit(QLineEdit):
    """The typing box: Enter applies, Esc or clicking away cancels."""
    committed = Signal(str)
    cancelled = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(EDIT_QSS)
        self.setMaxLength(8)
        self.setAlignment(Qt.AlignCenter)
        self._open = False

    def begin(self, text: str):
        self._open = True
        self.setText(text)
        self.setFocus(Qt.OtherFocusReason)
        self.selectAll()

    def _finish(self, signal, *args):
        if self._open:
            self._open = False
            signal.emit(*args)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            self._finish(self.committed, self.text())
            event.accept()
        elif event.key() == Qt.Key_Escape:
            self._finish(self.cancelled)
            event.accept()
        else:
            super().keyPressEvent(event)

    def focusOutEvent(self, event):
        super().focusOutEvent(event)
        self._finish(self.cancelled)


class SpeedPopup(QWidget):
    """
    Speed panel: pinned presets as a vertical list (max 6, each removable via a hover x), and under it a
    pin toggle for the current speed, the current speed (click to type one in) and a 0.05x precision slider.
    """
    speed_selected = Signal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("SpeedPopupWidget")
        # A child widget of the main window (like the volume popup). A separate
        # translucent Qt.Popup window rendered garbled here (video showing
        # through, stale chips), so the panel lives inside the window instead.
        # Without WA_StyledBackground a plain QWidget ignores the QSS background.
        self.setFixedWidth(PANEL_WIDTH)
        self._anchor = None
        self.hide()

        self.settings = open_settings("SpeedSettings")
        self._current_speed = 1.0
        self.presets = self._load_presets()

        self._init_ui()

    def paintEvent(self, event):
        p = QPainter(self)
        paint_glass_panel(p, QRectF(self.rect()), 16, calm=True)

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
        main.setContentsMargins(PAD_X, PAD_TOP, PAD_X, PAD_BOTTOM)
        main.setSpacing(8)

        # Header: title, how many presets are pinned, reset
        header = QHBoxLayout()
        header.setSpacing(6)
        title = QLabel("재생 속도", self)
        title.setStyleSheet("font-size: 12px; font-weight: 600; color: rgba(255, 255, 255, 0.7);")
        header.addWidget(title)

        self.lbl_count = QLabel("", self)
        self.lbl_count.setStyleSheet(COUNT_QSS)
        header.addWidget(self.lbl_count)
        header.addStretch()

        self.btn_reset = GlassButton(self, "pill", 20, text_px=11, text_pad=9, calm=True)
        self.btn_reset.setText("기본값")
        self.btn_reset.setToolTip("프리셋을 기본 구성으로 되돌리기")
        self.btn_reset.clicked.connect(self._reset_to_default_presets)
        header.addWidget(self.btn_reset)
        main.addLayout(header)

        # Preset list (one row each)
        self.preset_container = QWidget(self)
        self.preset_container.setObjectName("SpeedPresetList")
        self.preset_container.setStyleSheet("QWidget#SpeedPresetList { background: transparent; }")
        self.preset_layout = QVBoxLayout(self.preset_container)
        self.preset_layout.setContentsMargins(0, 0, 0, 0)
        self.preset_layout.setSpacing(3)
        main.addWidget(self.preset_container)

        # Bottom row: pin, the current speed (click to type), slider 0.25x .. 3.00x in 0.05x steps (25..300, step 5)
        bottom = QHBoxLayout()
        bottom.setSpacing(3)
        self.btn_pin = GlassButton(self, "plain", ROW_HEIGHT, icon_px=18)
        self.btn_pin.clicked.connect(self._on_pin_clicked)
        bottom.addWidget(self.btn_pin)

        self.value_box = QWidget(self)
        self.value_box.setObjectName("SpeedValueBox")
        self.value_box.setStyleSheet("QWidget#SpeedValueBox { background: transparent; }")
        self.value_box.setFixedSize(VALUE_WIDTH, ROW_HEIGHT)
        stack = QStackedLayout(self.value_box)
        stack.setContentsMargins(0, 0, 0, 0)
        self._value_stack = stack
        self.lbl_speed_val = _SpeedValueLabel(self.value_box)
        self.lbl_speed_val.clicked.connect(self._begin_speed_edit)
        stack.addWidget(self.lbl_speed_val)
        self.edit_speed = _SpeedEdit(self.value_box)
        self.edit_speed.committed.connect(self._commit_speed_edit)
        self.edit_speed.cancelled.connect(self._end_speed_edit)
        stack.addWidget(self.edit_speed)
        bottom.addWidget(self.value_box)

        self.slider = GlassSlider(Qt.Horizontal, self, snap_step=5)
        self.slider.setRange(25, 300)
        self.slider.setSingleStep(5)
        self.slider.setPageStep(10)
        self.slider.setValue(100)
        self.slider.setFixedHeight(ROW_HEIGHT)
        self.slider.valueChanged.connect(self._on_slider_value_changed)
        bottom.addWidget(self.slider, stretch=1)
        main.addLayout(bottom)

        self._flash_timer = QTimer(self)
        self._flash_timer.setSingleShot(True)
        self._flash_timer.setInterval(2200)
        self._flash_timer.timeout.connect(self._reset_flash)

        self._rebuild_preset_buttons()
        self._refresh_pin_state()

    def _reset_flash(self):
        self.lbl_count.setStyleSheet(COUNT_QSS)

    def _flash_hint(self, text: str = ""):
        """The preset list is full: the 6/6 counter lights up for a moment."""
        self.lbl_count.setStyleSheet(COUNT_FLASH_QSS)
        self._flash_timer.start()

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
            chip.show()                    # (a widget added to a shown parent only appears a turn later: too late to measure)
        self._refresh_pin_state()
        self._fit()

    def _fit(self):
        """The list got shorter / longer: resize the panel, keeping it right above its anchor."""
        self.layout().activate()
        self.adjustSize()
        if self.isVisible():
            self._place()

    def _is_pinned(self, value: float) -> bool:
        return any(abs(value - p) < 0.001 for p in self.presets)

    def _refresh_pin_state(self):
        full = len(self.presets) >= MAX_PRESETS
        pinned = self._is_pinned(self._current_speed)
        if pinned:
            self.btn_pin.setIcon(get_svg_icon("pin_fill", size=18, color="#FFFFFF"))
            self.btn_pin.setToolTip("고정 해제 (프리셋에서 제거)")
        elif full:
            self.btn_pin.setIcon(get_svg_icon("pin", size=18, color="#7A7F8C"))
            self.btn_pin.setToolTip(f"프리셋은 최대 {MAX_PRESETS}개입니다. 먼저 하나를 삭제하세요")
        else:
            self.btn_pin.setIcon(get_svg_icon("pin", size=18))
            self.btn_pin.setToolTip("현재 배속을 프리셋에 고정")
        self.lbl_count.setText(f"{len(self.presets)}/{MAX_PRESETS}")

    # --- preset editing ---------------------------------------------------

    def _on_pin_clicked(self):
        value = round(self.slider.value() / 100.0, 2)
        if self._is_pinned(value):
            self._unpin_preset(self._match_preset(value))
        elif not self._pin_current_speed():
            self._flash_hint()

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

    # --- typing a speed in ------------------------------------------------

    def _begin_speed_edit(self):
        self._value_stack.setCurrentWidget(self.edit_speed)
        self.edit_speed.begin(f"{self._current_speed:.2f}")

    def _end_speed_edit(self):
        self._value_stack.setCurrentWidget(self.lbl_speed_val)
        self.edit_speed.clearFocus()

    def _commit_speed_edit(self, text: str):
        speed = parse_speed_input(text)
        self._end_speed_edit()
        if speed is not None:
            self.slider.setValue(int(round(speed * 100)))

    def is_editing_speed(self) -> bool:
        return self._value_stack.currentWidget() is self.edit_speed

    # --- speed ------------------------------------------------------------

    def _on_slider_value_changed(self, raw_val: int):
        snapped = round(raw_val / 5.0) * 5  # snap to 0.05 steps
        spd = round(snapped / 100.0, 2)
        self.lbl_speed_val.setText(f"{spd:.2f}x")
        previous = self._current_speed
        self._current_speed = spd
        self.speed_selected.emit(spd)
        # Rows only change look when the active preset changes.
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

    def _place(self):
        """Float above the anchor, kept inside the parent window."""
        target, parent = self._anchor, self.parentWidget()
        if target is None or parent is None:
            return
        pos = target.mapTo(parent, QPoint(0, 0))
        x = pos.x() + (target.width() - self.width()) // 2
        y = pos.y() - self.height() - 10
        x = max(8, min(x, parent.width() - self.width() - 8))
        y = max(8, y)
        self.move(x, y)

    def show_above_widget(self, target_widget: QWidget):
        """Float the panel above `target_widget`, kept inside the parent window."""
        self._anchor = target_widget
        self.adjustSize()
        self._place()
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
        if hasattr(self, "_value_stack") and self.is_editing_speed():    # (hidden once before the UI exists)
            self._end_speed_edit()

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
