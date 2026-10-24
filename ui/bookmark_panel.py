"""
The bookmark list panel: opens above the bookmark button (Shift+B). One row per bookmark of the loaded video (amber dot, the
name or the time, the time); a click on a row goes there, the pencil renames it, the cross deletes it. The panel only asks
(signals): the owner changes the bookmarks and hands the new list back through `set_items`.
"""
from PySide6.QtCore import QEvent, QPoint, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import QApplication, QHBoxLayout, QLabel, QLineEdit, QPushButton, QScrollArea, QVBoxLayout, QWidget

from core import bookmarks
from core.media_info import format_clock
from ui.glass_button import GlassButton, paint_glass_panel
from ui.timeline_slider import PIN_COLOR

PANEL_WIDTH = 380
PAD = 12
ROW_HEIGHT = 44
VISIBLE_ROWS = 7                      # more rows than this scroll
EMPTY_HEIGHT = 64
FONT_FAMILY = "Segoe UI Variable Text"

TEXT = QColor(255, 255, 255, 230)
TEXT_DIM = QColor(255, 255, 255, 90)
META = QColor(255, 255, 255, 140)
HOVER_FILL = QColor(255, 255, 255, 18)

EDIT_QSS = (f'QLineEdit {{ background: rgba(255, 255, 255, 0.10); color: #FFFFFF; border: 1px solid rgba(255, 255, 255, 0.28);'
            f' border-radius: 8px; padding: 0 8px; font-family: "{FONT_FAMILY}", "Segoe UI", sans-serif; font-size: 13px; }}')
SCROLL_QSS = ('QScrollArea { background: transparent; border: none; } QScrollArea > QWidget > QWidget { background: transparent; }'
              ' QScrollBar:vertical { background: transparent; width: 6px; margin: 2px; }'
              ' QScrollBar::handle:vertical { background: rgba(255, 255, 255, 0.25); border-radius: 2px; min-height: 24px; }'
              ' QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }'
              ' QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }')


def _font(px: int, bold=False) -> QFont:
    f = QFont(FONT_FAMILY)
    f.setFamilies([FONT_FAMILY, "Segoe UI"])
    f.setPixelSize(px)
    f.setBold(bold)
    return f


def _label(text: str, px: int, alpha: float, bold=False, parent=None) -> QLabel:
    lbl = QLabel(text, parent)
    lbl.setStyleSheet(f'QLabel {{ background: transparent; color: rgba(255, 255, 255, {alpha}); font-family: "{FONT_FAMILY}",'
                      f' "Segoe UI", sans-serif; font-size: {px}px; font-weight: {700 if bold else 400}; }}')
    return lbl


class _IconButton(QPushButton):
    """A small round hover button on a row: a pencil or a cross."""

    def __init__(self, kind: str, parent=None):
        super().__init__(parent)
        self.kind = kind
        self.setFixedSize(26, 26)
        self.setFocusPolicy(Qt.NoFocus)
        self.setCursor(Qt.PointingHandCursor)
        self.setFlat(True)
        self._over = False

    def enterEvent(self, event):
        self._over = True
        self.update()

    def leaveEvent(self, event):
        self._over = False
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        if self._over:
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(255, 255, 255, 30))
            p.drawEllipse(QRectF(self.rect()))
        p.setPen(QPen(QColor(255, 255, 255, 215 if self._over else 150), 1.5, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        c = self.rect().center()
        cx, cy = c.x() + 0.5, c.y() + 0.5
        if self.kind == "delete":
            p.drawLine(QPoint(int(cx - 4), int(cy - 4)), QPoint(int(cx + 4), int(cy + 4)))
            p.drawLine(QPoint(int(cx - 4), int(cy + 4)), QPoint(int(cx + 4), int(cy - 4)))
        else:                                                     # a pencil: the body and its tip
            p.drawLine(QPoint(int(cx - 4), int(cy + 4)), QPoint(int(cx + 3), int(cy - 3)))
            p.drawLine(QPoint(int(cx + 3), int(cy - 3)), QPoint(int(cx + 5), int(cy - 5)))
            p.drawLine(QPoint(int(cx - 5), int(cy + 5)), QPoint(int(cx - 3), int(cy + 5)))


class _NameEdit(QLineEdit):
    committed = Signal(str)
    cancelled = Signal()

    def __init__(self, text: str, hint: str, parent=None):
        super().__init__(text, parent)
        self.setPlaceholderText(hint)
        self.setStyleSheet(EDIT_QSS)
        self.setMaxLength(60)
        self._done = False
        self.returnPressed.connect(self._commit)

    def _commit(self):
        if not self._done:
            self._done = True
            self.committed.emit(self.text().strip())

    def _cancel(self):
        if not self._done:
            self._done = True
            self.cancelled.emit()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self._cancel()
            event.accept()
            return
        super().keyPressEvent(event)
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            event.accept()                   # (a QLineEdit leaves it unaccepted, and it would go on up to the player)

    def focusOutEvent(self, event):
        super().focusOutEvent(event)
        self._cancel()


class _BookmarkRow(QWidget):
    jump = Signal(float)
    rename = Signal(float, str)
    delete = Signal(float)
    edit_started = Signal(object)
    edit_ended = Signal(object)

    def __init__(self, item: dict, dimmed: bool, parent=None):
        super().__init__(parent)
        self.item = item
        self.t = item["t"]
        self.dimmed = dimmed
        self._hover = False
        self._edit = None
        self.setFixedHeight(ROW_HEIGHT)
        self.setCursor(Qt.ArrowCursor if dimmed else Qt.PointingHandCursor)
        self.edit_button = _IconButton("edit", self)
        self.delete_button = _IconButton("delete", self)
        self.edit_button.clicked.connect(self.begin_edit)
        self.delete_button.clicked.connect(lambda: self.delete.emit(self.t))
        for b in (self.edit_button, self.delete_button):
            b.hide()

    def name_text(self) -> str:
        return bookmarks.display_name(self.item)

    def time_text(self) -> str:
        return format_clock(self.t)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        y = (self.height() - 26) // 2
        self.delete_button.move(self.width() - 8 - 26, y)
        self.edit_button.move(self.width() - 8 - 52, y)
        if self._edit is not None:
            self._edit.setGeometry(*self._edit_geometry())

    def _edit_geometry(self):
        return 30, (self.height() - 30) // 2, self.width() - 30 - 12, 30

    def enterEvent(self, event):
        self._hover = True
        if self._edit is None:
            self.edit_button.show()
            self.delete_button.show()
        self.update()

    def leaveEvent(self, event):
        self._hover = False
        for b in (self.edit_button, self.delete_button):
            b.hide()
        self.update()

    def begin_edit(self):
        if self._edit is not None:
            return
        self.edit_button.hide()
        self.delete_button.hide()
        self._edit = _NameEdit(self.item["name"], self.time_text(), self)
        self._edit.setGeometry(*self._edit_geometry())
        self._edit.committed.connect(self._commit)
        self._edit.cancelled.connect(self.end_edit)
        self._edit.show()
        self._edit.setFocus()
        self._edit.selectAll()
        self.edit_started.emit(self)
        self.update()

    def _commit(self, name: str):
        self.end_edit()
        self.rename.emit(self.t, name)

    def end_edit(self):
        edit, self._edit = self._edit, None
        if edit is not None:
            edit.hide()
            edit.setParent(None)
            edit.deleteLater()
            self.edit_ended.emit(self)
            self.update()

    def mouseReleaseEvent(self, event):
        if (event.button() == Qt.LeftButton and not self.dimmed and self._edit is None
                and self.rect().contains(event.position().toPoint())):
            self.jump.emit(self.t)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect())
        if self._hover and not self.dimmed:
            p.setPen(Qt.NoPen)
            p.setBrush(HOVER_FILL)
            p.drawRoundedRect(r, 9, 9)
        dot = QColor(PIN_COLOR)
        if self.dimmed:
            dot.setAlpha(90)
        p.setPen(Qt.NoPen)
        p.setBrush(dot)
        p.drawEllipse(QRectF(14, r.height() / 2 - 4, 8, 8))
        if self._edit is not None:
            return
        time_right = r.width() - 14
        if self._hover:
            time_right = r.width() - 8 - 52 - 6
        p.setFont(_font(12))
        time_w = QFontMetrics(p.font()).horizontalAdvance(self.time_text())
        p.setPen(TEXT_DIM if self.dimmed else META)
        p.drawText(QRectF(time_right - time_w, 0, time_w, r.height()), Qt.AlignVCenter | Qt.AlignRight, self.time_text())
        p.setFont(_font(13))
        fm = QFontMetrics(p.font())
        name_rect = QRectF(34, 0, max(0.0, time_right - time_w - 10 - 34), r.height())
        p.setPen(TEXT_DIM if self.dimmed else TEXT)
        p.drawText(name_rect, Qt.AlignVCenter | Qt.AlignLeft, fm.elidedText(self.name_text(), Qt.ElideRight, int(name_rect.width())))


class BookmarkPanel(QWidget):
    jump_requested = Signal(float)
    add_requested = Signal()
    rename_requested = Signal(float, str)
    delete_requested = Signal(float)
    opened = Signal()                    # just before it shows: the owner hands over the current bookmarks

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("BookmarkPanelWidget")
        self.setFixedWidth(PANEL_WIDTH)
        self.setFocusPolicy(Qt.StrongFocus)
        self._anchor = None
        self._above = None
        self._align_to = None
        self._editing_row = None
        self.hide()

        main = QVBoxLayout(self)
        main.setContentsMargins(PAD, PAD, PAD, PAD)
        main.setSpacing(6)

        head = QHBoxLayout()
        head.setContentsMargins(6, 0, 0, 0)
        head.setSpacing(8)
        head.addWidget(_label("북마크", 14, 1.0, bold=True, parent=self))
        self.count_label = _label("0개", 12, 0.5, parent=self)
        head.addWidget(self.count_label)
        head.addStretch()
        self.add_button = GlassButton(self, "pill", 30, width=112, text_px=13, text_pad=12, calm=True)
        self.add_button.setText("지금 위치  B")
        self.add_button.clicked.connect(self.add_requested.emit)
        head.addWidget(self.add_button)
        main.addLayout(head)

        self._scroll = QScrollArea(self)
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QScrollArea.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._scroll.setStyleSheet(SCROLL_QSS)
        for part in (self._scroll, self._scroll.viewport(), self._scroll.verticalScrollBar()):
            part.setFocusPolicy(Qt.NoFocus)           # (a click in the list must not hand the focus to the scroll area: it eats the arrow keys)
        self._body = QWidget()
        self._list = QVBoxLayout(self._body)
        self._list.setContentsMargins(0, 0, 0, 0)
        self._list.setSpacing(0)
        self._scroll.setWidget(self._body)
        main.addWidget(self._scroll)

        self.empty_label = _label("아직 북마크가 없어요 · B 로 지금 위치를 저장해요", 13, 0.5, parent=self._body)
        self.empty_label.setAlignment(Qt.AlignCenter)
        self.empty_label.setFixedHeight(EMPTY_HEIGHT)
        self.hint_label = _label("이전 / 다음 북마크: Alt + ← / Alt + →", 11, 0.4, parent=self)
        self.hint_label.setContentsMargins(6, 0, 0, 0)
        main.addWidget(self.hint_label)

    def paintEvent(self, event):
        p = QPainter(self)
        paint_glass_panel(p, QRectF(self.rect()), 16, calm=True)

    # --- content ----------------------------------------------------------

    @property
    def is_editing(self) -> bool:
        """A rename field is open: the owner leaves the keys to it (typing a name must not trigger the player's keys)."""
        return self._editing_row is not None

    def set_items(self, items: list, duration: float):
        """Show `items` ([{"t", "name"}]); one beyond `duration` is dimmed and cannot be jumped to."""
        self._editing_row = None
        while self._list.count():
            widget = self._list.takeAt(0).widget()
            if widget is not None and widget is not self.empty_label:
                widget.hide()
                widget.setParent(None)
                widget.deleteLater()
        for item in items:
            row = _BookmarkRow(item, duration > 0 and item["t"] > duration, self._body)
            row.jump.connect(self.jump_requested.emit)
            row.rename.connect(self.rename_requested.emit)
            row.delete.connect(self.delete_requested.emit)
            row.edit_started.connect(self._on_edit_started)
            row.edit_ended.connect(self._on_edit_ended)
            self._list.addWidget(row)
            row.show()
        self._list.addWidget(self.empty_label)
        self.empty_label.setVisible(not items)
        self.count_label.setText(f"{len(items)}개")
        self._scroll.setFixedHeight(EMPTY_HEIGHT if not items else min(len(items), VISIBLE_ROWS) * ROW_HEIGHT)
        self._fit()

    def _on_edit_started(self, row):
        self._editing_row = row

    def _on_edit_ended(self, row):
        if self._editing_row is row:
            self._editing_row = None
        self.setFocus()                  # (so Escape reaches the panel and the next one closes it)

    # --- showing / dismissing ---------------------------------------------

    def _fit(self):
        self.layout().activate()
        self.adjustSize()
        if self.isVisible():
            self._place()

    def _place(self):
        """Above the anchor, in the bottom-right corner (as the audio / subtitle panel), kept inside the parent window."""
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
        self.opened.emit()
        self.adjustSize()
        self._place()
        self.show()
        self.raise_()
        self.setFocus()

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
        self._editing_row = None
        focus = QApplication.focusWidget()
        if focus is not None and (focus is self or self.isAncestorOf(focus)):
            focus.clearFocus()                        # (closed: the keys go back to the player)

    def eventFilter(self, obj, event):
        # A click outside the panel (and not on its own button) dismisses it.
        if self.isVisible() and event.type() == QEvent.MouseButtonPress:
            g = event.globalPosition().toPoint()
            inside = self.rect().contains(self.mapFromGlobal(g))
            on_anchor = self._anchor is not None and self._anchor.rect().contains(self._anchor.mapFromGlobal(g))
            if not inside and not on_anchor:
                self.hide()
        return super().eventFilter(obj, event)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.hide()
        else:
            super().keyPressEvent(event)
