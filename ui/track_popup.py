"""
The audio / subtitle panel: opens above the subtitle button, with a tab for each. A tab is a list of tracks (one
selected; the name on the left, codec / source on the right), the sync value with its keys, and for subtitles the
on/off switch and "load an external file".
"""
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QApplication
from PySide6.QtCore import Qt, Signal, QPoint, QRectF, QEvent
from PySide6.QtGui import QPainter, QColor, QFont, QFontMetrics, QPen

from core.tracks import format_delay
from ui.glass_button import GlassButton, paint_glass_panel
from ui.glass_switch import GlassSwitch as _Switch

PANEL_WIDTH = 280
PAD = 12
ROW_HEIGHT = 30
TAB_HEIGHT = 30
TAB_WIDTH = (PANEL_WIDTH - 2 * PAD - 4) // 2
FONT_FAMILY = "Segoe UI Variable Text"

TEXT = QColor(255, 255, 255, 168)
TEXT_ON = QColor(255, 255, 255, 255)
META = QColor(255, 255, 255, 128)
META_ON = QColor(255, 255, 255, 192)
HOVER_FILL = QColor(255, 255, 255, 18)
ON_FILL = QColor(255, 255, 255, 26)
LINE = QColor(255, 255, 255, 36)

SUB_TAB, AUDIO_TAB = "sub", "audio"

LABEL_QSS = f'QLabel {{ background: transparent; color: rgba(255, 255, 255, 0.55); font-family: "{FONT_FAMILY}", "Segoe UI", sans-serif; font-size: 12px; }}'
VALUE_QSS = f'QLabel {{ background: transparent; color: #FFFFFF; font-family: "{FONT_FAMILY}", "Segoe UI", sans-serif; font-size: 12px; font-weight: 700; }}'
NOTE_QSS = f'QLabel {{ background: transparent; color: rgba(255, 255, 255, 0.5); font-family: "{FONT_FAMILY}", "Segoe UI", sans-serif; font-size: 13px; }}'


def _font(px: int, bold=False) -> QFont:
    f = QFont(FONT_FAMILY)
    f.setFamilies([FONT_FAMILY, "Segoe UI"])
    f.setPixelSize(px)
    f.setBold(bold)
    return f


class _Row(QWidget):
    """One line: a radio dot (tracks) or a plus (actions), the name, and a small detail at the right end."""
    clicked = Signal()

    def __init__(self, name: str, detail: str = "", selected: bool = False, plus: bool = False, parent=None):
        super().__init__(parent)
        self.name, self.detail, self.selected, self.plus = name, detail, selected, plus
        self._hover = False
        self.setFixedHeight(ROW_HEIGHT)
        self.setCursor(Qt.PointingHandCursor)

    def enterEvent(self, event):
        self._hover = True
        self.update()

    def leaveEvent(self, event):
        self._hover = False
        self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self.rect().contains(event.position().toPoint()):
            self.clicked.emit()
            event.accept()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect())
        if self.selected or self._hover:
            p.setPen(Qt.NoPen)
            p.setBrush(ON_FILL if self.selected else HOVER_FILL)
            p.drawRoundedRect(r, 9, 9)

        cx, cy = 20.0, r.height() / 2
        if self.plus:
            p.setPen(QPen(TEXT_ON, 1.6, Qt.SolidLine, Qt.RoundCap))
            p.drawLine(int(cx - 5), int(cy), int(cx + 5), int(cy))
            p.drawLine(int(cx), int(cy - 5), int(cx), int(cy + 5))
        else:
            p.setBrush(Qt.NoBrush)
            if self.selected:
                p.setPen(Qt.NoPen)
                p.setBrush(TEXT_ON)
                p.drawEllipse(QRectF(cx - 7, cy - 7, 14, 14))
                p.setBrush(QColor(22, 24, 33, 255))
                p.drawEllipse(QRectF(cx - 3, cy - 3, 6, 6))
            else:
                p.setPen(QPen(QColor(255, 255, 255, 115), 1.5))
                p.drawEllipse(QRectF(cx - 6.5, cy - 6.5, 13, 13))

        right = r.width() - 10
        if self.detail:
            p.setFont(_font(12))
            fm = QFontMetrics(p.font())
            w = fm.horizontalAdvance(self.detail)
            p.setPen(META_ON if self.selected else META)
            p.drawText(QRectF(right - w, 0, w, r.height()), Qt.AlignVCenter | Qt.AlignRight, self.detail)
            right -= w + 10
        p.setFont(_font(13, bold=self.selected))
        fm = QFontMetrics(p.font())
        text_rect = QRectF(36, 0, max(0.0, right - 36), r.height())
        p.setPen(TEXT_ON if (self.selected or self.plus or self._hover) else TEXT)
        p.drawText(text_rect, Qt.AlignVCenter | Qt.AlignLeft, fm.elidedText(self.name, Qt.ElideRight, int(text_rect.width())))


class _Divider(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(11)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setPen(LINE)
        p.drawLine(4, 5, self.width() - 4, 5)


class TrackPopup(QWidget):
    audio_chosen = Signal(int)
    subtitle_chosen = Signal(int)
    subtitles_toggled = Signal(bool)
    load_subtitle_requested = Signal()
    opened = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("TrackPopupWidget")
        self.setFixedWidth(PANEL_WIDTH)
        self._anchor = None
        self._above = None             # the panel floats just over the top of this widget (the seek bar), else the anchor
        self._align_to = None          # the panel's right edge lines up with this widget's right edge (when it is shown)
        self._tab = SUB_TAB
        self._data = dict(audio=[], subs=[], sub_visible=True, sub_delay=0.0, audio_delay=0.0)
        self.hide()

        main = QVBoxLayout(self)
        main.setContentsMargins(PAD, PAD, PAD, PAD)
        main.setSpacing(4)

        tabs = QHBoxLayout()
        tabs.setSpacing(4)
        self.btn_audio = self._tab_button("오디오", AUDIO_TAB)
        self.btn_sub = self._tab_button("자막", SUB_TAB)
        tabs.addWidget(self.btn_audio)
        tabs.addWidget(self.btn_sub)
        main.addLayout(tabs)

        self._body = QVBoxLayout()
        self._body.setContentsMargins(0, 4, 0, 0)
        self._body.setSpacing(2)
        main.addLayout(self._body)
        self._sync_tabs()

    def _tab_button(self, text: str, tab: str) -> GlassButton:
        b = GlassButton(self, "pill", TAB_HEIGHT, width=TAB_WIDTH, text_px=13, text_pad=12, calm=True)
        b.setText(text)
        b.clicked.connect(lambda: self.set_tab(tab))
        return b

    def paintEvent(self, event):
        p = QPainter(self)
        paint_glass_panel(p, QRectF(self.rect()), 16, calm=True)

    # --- content ----------------------------------------------------------

    @property
    def tab(self) -> str:
        return self._tab

    def set_tab(self, tab: str):
        if tab != self._tab:
            self._tab = tab
            self._sync_tabs()
            self._rebuild()

    def _sync_tabs(self):
        for b, tab in ((self.btn_audio, AUDIO_TAB), (self.btn_sub, SUB_TAB)):
            b.setActive(self._tab == tab)

    def set_data(self, audio, subs, sub_visible, sub_delay, audio_delay):
        self._data = dict(audio=list(audio), subs=list(subs), sub_visible=bool(sub_visible),
                          sub_delay=sub_delay, audio_delay=audio_delay)
        self._rebuild()

    def _add(self, widget):
        self._body.addWidget(widget)
        widget.show()                     # a widget added to a shown parent only appears a turn later: too late to measure
        return widget

    def _note(self, text: str) -> QLabel:
        lbl = QLabel(text, self)
        lbl.setStyleSheet(NOTE_QSS)
        lbl.setContentsMargins(10, 8, 10, 8)
        return lbl

    def _sync_line(self, label: str, seconds: float, keys: str) -> QWidget:
        line = QWidget(self)
        h = QHBoxLayout(line)
        h.setContentsMargins(10, 2, 10, 2)
        h.setSpacing(8)
        a = QLabel(label, line)
        a.setStyleSheet(LABEL_QSS)
        v = QLabel(format_delay(seconds), line)
        v.setStyleSheet(VALUE_QSS)
        k = QLabel(keys, line)
        k.setStyleSheet(LABEL_QSS)
        h.addWidget(a)
        h.addWidget(v)
        h.addStretch()
        h.addWidget(k)
        return line

    def _rebuild(self):
        while self._body.count():
            widget = self._body.takeAt(0).widget()
            if widget:
                widget.hide()
                widget.setParent(None)
                widget.deleteLater()

        d = self._data
        if self._tab == SUB_TAB:
            self._build_subtitles(d)
        else:
            self._build_audio(d)
        self._fit()

    def _build_audio(self, d):
        if not d["audio"]:
            self._add(self._note("오디오 트랙이 없습니다"))
        for t in d["audio"]:
            row = self._add(_Row(t.name, t.detail, t.selected, parent=self))
            row.clicked.connect(lambda tid=t.id: self.audio_chosen.emit(tid))
        self._add(_Divider(self))
        self._add(self._sync_line("지연", d["audio_delay"], "Shift+Z / X"))

    def _build_subtitles(self, d):
        subs = d["subs"]
        head = QWidget(self)
        h = QHBoxLayout(head)
        h.setContentsMargins(10, 4, 4, 4)
        text = QLabel("자막 표시", head)
        text.setStyleSheet(f'QLabel {{ background: transparent; color: #FFFFFF; font-family: "{FONT_FAMILY}", "Segoe UI", sans-serif; font-size: 13px; }}')
        h.addWidget(text)
        h.addStretch()
        switch = _Switch(d["sub_visible"], head)
        switch.setEnabled(bool(subs))
        switch.toggled.connect(self.subtitles_toggled.emit)
        h.addWidget(switch)
        self._add(head)

        if not subs:
            self._add(self._note("이 영상에는 자막이 없습니다"))
        for t in subs:
            row = self._add(_Row(t.name, t.detail, t.selected and d["sub_visible"], parent=self))
            row.clicked.connect(lambda tid=t.id: self.subtitle_chosen.emit(tid))
        self._add(_Divider(self))
        self._add(self._sync_line("싱크", d["sub_delay"], "Z / X · 초기화 Ctrl+Z"))
        load = self._add(_Row("외부 자막 불러오기…", plus=True, parent=self))
        load.clicked.connect(self.load_subtitle_requested.emit)

    # --- showing / dismissing ---------------------------------------------

    def _fit(self):
        self.layout().activate()
        self.adjustSize()
        if self.isVisible():
            self._place()

    def _place(self):
        """Above the anchor, in the bottom-right corner: its right edge on the ``align_to`` widget's right edge (the
        controls' right margin), else on the anchor's. Kept inside the parent window."""
        target, parent = self._anchor, self.parentWidget()
        if target is None or parent is None:
            return
        pos = target.mapTo(parent, QPoint(0, 0))
        align = self._align_to
        if align is not None and align.isVisible():
            x = align.mapTo(parent, QPoint(0, 0)).x() + align.width() - self.width()
        else:
            x = pos.x() + target.width() - self.width()
        above = self._above
        top = above.mapTo(parent, QPoint(0, 0)).y() if above is not None and above.isVisible() else pos.y()
        y = top - self.height() - 10
        self.move(max(8, min(x, parent.width() - self.width() - 8)), max(8, y))

    def show_above_widget(self, target_widget: QWidget, align_to: QWidget = None, above: QWidget = None):
        self._anchor = target_widget
        self._align_to = align_to
        self._above = above
        self.opened.emit()                 # the owner fills in the current tracks
        self.adjustSize()
        self._place()
        self.show()
        self.raise_()

    def toggle_above_widget(self, target_widget: QWidget, align_to: QWidget = None, above: QWidget = None):
        if self.isVisible():
            self.hide()
        else:
            self.show_above_widget(target_widget, align_to, above)

    def showEvent(self, event):
        super().showEvent(event)
        QApplication.instance().installEventFilter(self)

    def hideEvent(self, event):
        super().hideEvent(event)
        QApplication.instance().removeEventFilter(self)

    def eventFilter(self, obj, event):
        # A click outside the panel (and not on its own button) dismisses it.
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
