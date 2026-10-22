"""
The settings panel: a glass panel laid over the player window (not a window of its own: a second translucent window
made the player flicker when it opened, since the player was deactivated and repainted) with a tab for each topic.

    설정                 ( 컨트롤 배치 | 성능 | 오디오 )                  ×

* 컨트롤 배치: edit the control bar the way it looks (``LayoutEditor``); it keeps 기본값 복원 / 취소 / 적용.
* 성능, 오디오, 일반: one row per option with a switch, applied the moment it is clicked (``hwdec_changed``,
  ``lecture_audio_changed``, ``updates_changed``); these tabs only have 닫기.

``open()`` shows it, ``accept()`` / ``reject()`` close it; ``layout_changed`` carries the new layout on Apply and
``finished(accepted)`` fires when it closes. While it is open it keeps the keyboard (Esc closes, every other key is
swallowed) and the dim layer keeps the mouse, so nothing behind it reacts. The panel keeps one size whatever the tab.
"""
from PySide6.QtCore import QEvent, Qt, QRectF, Signal
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QGraphicsOpacityEffect, QHBoxLayout, QLabel, QStackedLayout, QVBoxLayout, QWidget

from ui.glass_button import GlassButton, paint_glass_panel
from ui.glass_switch import GlassSwitch
from ui.icons import get_svg_icon
from ui.layout_dialog import DIALOG_CONTENT_W, DIALOG_MARGIN, LayoutEditor

LAYOUT_TAB, PERFORMANCE_TAB, AUDIO_TAB, GENERAL_TAB = "layout", "performance", "audio", "general"
TAB_TITLES = {LAYOUT_TAB: "컨트롤 배치", PERFORMANCE_TAB: "성능", AUDIO_TAB: "오디오", GENERAL_TAB: "일반"}
TAB_WIDTH, TAB_HEIGHT = 104, 30
FONT = '"Segoe UI Variable Text", "Segoe UI", sans-serif'

TITLE_QSS = f"color: #FFFFFF; font-size: 17px; font-weight: 600; background: transparent; font-family: {FONT};"
DESC_QSS = f"color: rgba(255, 255, 255, 0.5); font-size: 12px; background: transparent; font-family: {FONT};"
ROW_TITLE_QSS = f"color: #FFFFFF; font-size: 14px; font-weight: 600; background: transparent; font-family: {FONT};"
ROW_DESC_QSS = f"color: rgba(255, 255, 255, 0.55); font-size: 12px; background: transparent; font-family: {FONT};"

# The option rows of the 성능 / 오디오 tabs: (title, description). Switching one is applied at once.
HWDEC_ROW = ("하드웨어 디코딩", "GPU로 영상을 풉니다. 화면이 안 나오거나 깨지면 꺼 보세요.")
LECTURE_ROW = ("강의 음성", "먹먹한 목소리를 또렷하게 하고, 작은 소리는 키우고 큰 소리는 눌러 줍니다. "
                          "켜 두면 오디오 트랙은 1번으로 고정됩니다.")


THUMBNAILS_ROW = ("재생바 썸네일", "재생바에 마우스를 올리면 그 위치의 장면을 보여 줍니다.")
THUMBNAILS_STOP_ROW = ("마우스를 멈췄을 때만 표시", "훑는 동안은 시간만 보이고 잠깐 멈추면 장면이 나타나요. 4K 60fps처럼 영상이 끊길 때 켜 보세요.")
UPDATES_ROW = ("새 버전 알림", "하루에 한 번 새 버전이 있는지 확인하고, 있으면 알려 줘요. 꺼도 정보 창의 ‘업데이트 확인’은 쓸 수 있어요.")


class _Dim(QWidget):
    """Darkens the window behind the panel and swallows the mouse, which is what makes the panel modal."""

    def __init__(self, window):
        super().__init__(window)
        self.setGeometry(window.rect())
        self.setFocusPolicy(Qt.NoFocus)

    def paintEvent(self, event):
        QPainter(self).fillRect(self.rect(), QColor(0, 0, 0, 118))

    def mousePressEvent(self, event):
        event.accept()

    def mouseReleaseEvent(self, event):
        event.accept()

    def mouseDoubleClickEvent(self, event):
        event.accept()

    def wheelEvent(self, event):
        event.accept()

    def contextMenuEvent(self, event):
        event.accept()


class _SwitchRow(QWidget):
    """A title and a one-line description on the left, the switch on the right; a click anywhere on the row flips it."""

    def __init__(self, title: str, description: str, checked: bool, parent=None):
        super().__init__(parent)
        self.setCursor(Qt.PointingHandCursor)
        row = QHBoxLayout(self)
        row.setContentsMargins(4, 14, 4, 14)
        row.setSpacing(24)
        texts = QVBoxLayout()
        texts.setSpacing(4)
        head = QLabel(title, self)
        head.setStyleSheet(ROW_TITLE_QSS)
        desc = QLabel(description, self)
        desc.setStyleSheet(ROW_DESC_QSS)
        desc.setWordWrap(True)
        for label in (head, desc):
            label.setAttribute(Qt.WA_TransparentForMouseEvents)        # the row takes the click
        texts.addWidget(head)
        texts.addWidget(desc)
        row.addLayout(texts, 1)
        self.switch = GlassSwitch(checked, self)
        row.addWidget(self.switch, 0, Qt.AlignVCenter)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self.rect().contains(event.position().toPoint()):
            if not self.switch.geometry().contains(event.position().toPoint()):     # (the switch handles its own click)
                self.switch.checked = not self.switch.checked
                self.switch.update()
                self.switch.toggled.emit(self.switch.checked)
        event.accept()


class SettingsPanel(QWidget):
    layout_changed = Signal(dict)
    finished = Signal(bool)
    hwdec_changed = Signal(bool)
    lecture_audio_changed = Signal(bool)
    updates_changed = Signal(bool)
    thumbnails_changed = Signal(bool)
    thumbnails_on_stop_changed = Signal(bool)

    def __init__(self, current_layout: dict, metadata: dict, default_layout: dict, host: QWidget, *,
                 hwdec_on: bool = True, lecture_audio_on: bool = False, updates_on: bool = True,
                 thumbnails_on: bool = True, thumbnails_on_stop: bool = False):
        super().__init__(host)
        self._host = host
        self._default = default_layout
        self._dim = _Dim(host)
        self._dim.hide()
        self._moved = False            # dragged by its header: then it is kept where the user put it
        self._drag_from = None
        self._tab = LAYOUT_TAB
        self.setFocusPolicy(Qt.StrongFocus)

        m = DIALOG_MARGIN
        root = QVBoxLayout(self)
        root.setContentsMargins(m + 24, m + 22, m + 24, m + 20)
        root.setSpacing(0)

        # --- header: title | tabs | close (the two outer cells share the slack so the tabs sit in the middle)
        head = QHBoxLayout()
        title = QLabel("설정", self)
        title.setStyleSheet(TITLE_QSS)
        head.addWidget(title, 1, Qt.AlignVCenter)
        tabs = QHBoxLayout()
        tabs.setSpacing(4)
        self.btn_tab_layout = self._tab_button(LAYOUT_TAB)
        self.btn_tab_perf = self._tab_button(PERFORMANCE_TAB)
        self.btn_tab_audio = self._tab_button(AUDIO_TAB)
        self.btn_tab_general = self._tab_button(GENERAL_TAB)
        for b in (self.btn_tab_layout, self.btn_tab_perf, self.btn_tab_audio, self.btn_tab_general):
            tabs.addWidget(b)
        head.addLayout(tabs)
        right = QHBoxLayout()
        right.addStretch()
        self.btn_close = GlassButton(self, "flat", 28, icon_px=12, radius=14)
        self.btn_close.setIcon(get_svg_icon("close", size=12, color="#FFFFFF"))
        self.btn_close.setToolTip("닫기 (Esc)")
        self.btn_close.clicked.connect(self.reject)
        right.addWidget(self.btn_close, 0, Qt.AlignTop)
        head.addLayout(right, 1)
        root.addLayout(head)
        root.addSpacing(16)

        self._pages = QStackedLayout()
        self._pages.addWidget(self._build_layout_page(current_layout, metadata))
        self._pages.addWidget(self._build_options_page(
            [HWDEC_ROW, THUMBNAILS_ROW, THUMBNAILS_STOP_ROW], [hwdec_on, thumbnails_on, thumbnails_on_stop],
            ["row_hwdec", "row_thumbnails", "row_thumbnails_stop"],
            ["switch_hwdec", "switch_thumbnails", "switch_thumbnails_stop"],
            [self.hwdec_changed, self.thumbnails_changed, self.thumbnails_on_stop_changed], "btn_close_perf"))
        self._setup_thumbnail_rows(thumbnails_on)
        self._pages.addWidget(self._build_options_page(
            [LECTURE_ROW], [lecture_audio_on], ["row_lecture"], ["switch_lecture"], [self.lecture_audio_changed],
            "btn_close_audio"))
        self._pages.addWidget(self._build_options_page(
            [UPDATES_ROW], [updates_on], ["row_updates"], ["switch_updates"], [self.updates_changed], "btn_close_general"))
        root.addLayout(self._pages)

        root.activate()
        self.setFixedSize(self.sizeHint())
        self._sync_tabs()
        self.hide()
        host.installEventFilter(self)

    # --- building -----------------------------------------------------------------------------
    def _tab_button(self, tab: str) -> GlassButton:
        b = GlassButton(self, "pill", TAB_HEIGHT, width=TAB_WIDTH, text_px=13, text_pad=12, calm=True)
        b.setText(TAB_TITLES[tab])
        b.clicked.connect(lambda: self.set_tab(tab))
        return b

    def _foot_button(self, text: str, pad: int, bold: bool = False) -> GlassButton:
        b = GlassButton(self, "pill", 34, text_px=12, text_pad=pad, calm=not bold, bold=bold)
        b.setText(text)
        return b

    def _build_layout_page(self, current_layout: dict, metadata: dict) -> QWidget:
        page = QWidget(self)
        col = QVBoxLayout(page)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(0)
        desc = QLabel("컨트롤 바가 어떻게 보일지 그대로 보면서 배치하세요.", page)
        desc.setStyleSheet(DESC_QSS)
        col.addWidget(desc)
        col.addSpacing(12)

        self.editor = LayoutEditor(current_layout, metadata, self._default, page)
        self.editor.setFixedWidth(DIALOG_CONTENT_W - 48)
        self.editor.fit()                      # (its height depends on the layout; the panel needs it before painting)
        col.addWidget(self.editor)
        col.addSpacing(18)

        foot = QHBoxLayout()
        self.btn_reset = self._foot_button("기본값 복원", 18)
        self.btn_reset.clicked.connect(lambda: self.editor.set_layout(self._default))
        foot.addWidget(self.btn_reset)
        foot.addStretch()
        self.btn_cancel = self._foot_button("취소", 20)
        self.btn_cancel.clicked.connect(self.reject)
        foot.addWidget(self.btn_cancel)
        foot.addSpacing(8)
        self.btn_apply = self._foot_button("적용", 22, bold=True)
        self.btn_apply.clicked.connect(self._apply)
        foot.addWidget(self.btn_apply)
        col.addLayout(foot)
        return page

    def _build_options_page(self, rows, values, row_names, switch_names, signals, close_name) -> QWidget:
        page = QWidget(self)
        col = QVBoxLayout(page)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(0)
        for (title, desc), value, row_name, switch_name, signal in zip(rows, values, row_names, switch_names, signals):
            row = _SwitchRow(title, desc, value, page)
            row.switch.toggled.connect(signal.emit)
            setattr(self, row_name, row)
            setattr(self, switch_name, row.switch)
            col.addWidget(row)
        col.addStretch()
        foot = QHBoxLayout()
        foot.addStretch()
        close = self._foot_button("닫기", 22)
        close.clicked.connect(self.reject)
        setattr(self, close_name, close)
        foot.addWidget(close)
        col.addLayout(foot)
        return page

    def _setup_thumbnail_rows(self, thumbnails_on: bool):
        """The "only when the pointer rests" row belongs to the thumbnail row: indented under it, dimmed and inert
        while thumbnails are off."""
        row = self.row_thumbnails_stop
        margins = row.layout().contentsMargins()
        row.layout().setContentsMargins(margins.left() + 18, margins.top(), margins.right(), margins.bottom())
        self._stop_dim = QGraphicsOpacityEffect(row)
        row.setGraphicsEffect(self._stop_dim)
        self.switch_thumbnails.toggled.connect(self._sync_thumbnail_rows)
        self._sync_thumbnail_rows(thumbnails_on)

    def _sync_thumbnail_rows(self, thumbnails_on: bool):
        self.row_thumbnails_stop.setEnabled(bool(thumbnails_on))
        self._stop_dim.setOpacity(1.0 if thumbnails_on else 0.45)

    # --- tabs ---------------------------------------------------------------------------------
    @property
    def tab(self) -> str:
        return self._tab

    def set_tab(self, tab: str):
        self._tab = tab
        self._sync_tabs()

    def _sync_tabs(self):
        order = (LAYOUT_TAB, PERFORMANCE_TAB, AUDIO_TAB, GENERAL_TAB)
        self._pages.setCurrentIndex(order.index(self._tab))
        for b, tab in zip((self.btn_tab_layout, self.btn_tab_perf, self.btn_tab_audio, self.btn_tab_general), order):
            b.setActive(self._tab == tab)

    # --- opening / closing --------------------------------------------------------------------
    def open(self):
        self._dim.setGeometry(self._host.rect())
        self._dim.show()
        self._dim.raise_()
        self._place()
        self.show()
        self.raise_()
        self.setFocus(Qt.PopupFocusReason)

    def is_open(self) -> bool:
        return self.isVisible()

    def raise_overlay(self):
        """Back on top of everything (the window raises its floating widgets when it is laid out)."""
        self._dim.raise_()
        self.raise_()

    def accept(self):
        self._close(True)

    def reject(self):
        self._close(False)

    def _apply(self):
        self.layout_changed.emit(self.editor.layout())
        self.accept()

    def _close(self, accepted: bool):
        if self._dim is None:
            return
        self._host.removeEventFilter(self)
        self._dim.hide()
        self._dim.deleteLater()
        self._dim = None
        self.hide()
        self.deleteLater()
        self.finished.emit(accepted)

    # --- placing: centred in the window, following its size ---------------------------------------
    def _place(self):
        host = self._host.rect()
        if self._moved:
            x = max(0, min(self.x(), host.width() - self.width()))
            y = max(0, min(self.y(), host.height() - self.height()))
        else:
            x = (host.width() - self.width()) // 2
            y = (host.height() - self.height()) // 2
        self.move(x, y)

    def eventFilter(self, obj, event):
        if obj is self._host and event.type() == QEvent.Resize and self._dim is not None:
            self._dim.setGeometry(self._host.rect())
            self._place()
        return super().eventFilter(obj, event)

    # --- the keyboard and the header --------------------------------------------------------------
    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.reject()
        event.accept()                          # nothing reaches the player's shortcuts while this is open

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and event.position().y() < DIALOG_MARGIN + 70:
            self._drag_from = event.position().toPoint()
        event.accept()

    def mouseMoveEvent(self, event):
        if self._drag_from is not None:
            host = self._host.rect()
            target = self.mapToParent(event.position().toPoint() - self._drag_from)
            self.move(max(0, min(target.x(), host.width() - self.width())), max(0, min(target.y(), host.height() - self.height())))
            self._moved = True
        event.accept()

    def mouseReleaseEvent(self, event):
        self._drag_from = None
        event.accept()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        m = DIALOG_MARGIN
        panel = QRectF(m, m, self.width() - 2 * m, self.height() - 2 * m)
        p.setPen(Qt.NoPen)
        for i in range(10):                                    # a deep, soft shadow around the panel
            grow = i * 2.6
            p.setBrush(QColor(0, 0, 0, 9))
            p.drawRoundedRect(panel.translated(0, 10).adjusted(-grow, -grow, grow, grow), 24 + grow, 24 + grow)
        p.translate(panel.topLeft())
        paint_glass_panel(p, QRectF(0, 0, panel.width(), panel.height()), 24, calm=True)
