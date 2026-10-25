"""The shortcut help on the window: when it opens, which layout it takes, and what closes or re-places it. The panel itself is
``ui.help_panel.HelpPanel`` (made on the first open, then kept); the window only creates this and connects the title-bar
button, the key router (``?``, ``Esc``) and the right-click menu to it.

Stacking: the centred panel and its dim are above everything (it is modal); the drawer sits below the pop-ups of the
controls (bookmark list, tracks, speed, info), which stay usable over it, and keeps clear of the control strip."""
from PySide6.QtCore import QEvent, QObject, QRect, Qt
from PySide6.QtWidgets import QApplication, QWidget

from ui.help_panel import HelpPanel

CENTERED_MIN = (720, 460)               # a video area at least this big (with no video loaded) gets the centred panel
DRAWER_SPARE = 200                      # the drawer keeps clear of the control strip when at least this much is left


class HelpFlow(QObject):
    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self._panel = None              # made on first use

    # --- state --------------------------------------------------------------------------------------------------

    def is_open(self) -> bool:
        return self._panel is not None and self._panel.is_open()

    def is_modal(self) -> bool:
        """The centred layout owns the keyboard and the mouse; the drawer is a reference sheet beside a working player."""
        return self.is_open() and self._panel.kind == HelpPanel.CENTERED

    def layout_kind(self) -> str:
        area = self.window.viewport.geometry()
        if self.window._current_file is None and area.width() >= CENTERED_MIN[0] and area.height() >= CENTERED_MIN[1]:
            return HelpPanel.CENTERED
        return HelpPanel.DRAWER

    def _area(self, kind: str) -> QRect:
        area = QRect(self.window.viewport.geometry())
        if kind == HelpPanel.DRAWER:
            below = self.window.controller.CONTROLS_HEIGHT
            if area.height() - below - 46 - 14 >= DRAWER_SPARE:          # (a small window keeps the whole height)
                area.setHeight(area.height() - below)
        return area

    # --- opening and closing ------------------------------------------------------------------------------------

    def toggle(self):
        self.close() if self.is_open() else self.open()

    def open(self):
        if self._panel is None:
            self._panel = HelpPanel(self.window.central_widget)
            self._panel.close_requested.connect(self._close_from_dim)
        kind = self.layout_kind()
        self._panel.show_as(kind, self._area(kind))
        QApplication.instance().installEventFilter(self)
        self.window._reposition_floating_widgets()       # (the stacking order)

    def close(self, absorb_ms: int = 0):
        if self._panel is not None:
            self._panel.hide_help(absorb_ms)
        QApplication.instance().removeEventFilter(self)

    def _close_from_dim(self):
        self.close(absorb_ms=QApplication.doubleClickInterval())

    def relayout(self):
        """The window's size or mode changed: choose the layout again and place the panel."""
        if self.is_open():
            kind = self.layout_kind()
            self._panel.show_as(kind, self._area(kind))

    def raise_drawer(self):
        """(Early in the window's stacking order: the pop-ups of the controls are raised over it afterwards.)"""
        if self.is_open() and self._panel.kind == HelpPanel.DRAWER:
            self._panel.raise_()

    def raise_modal(self):
        """(Last: over the title bar, the controls and the update card.)"""
        if self.is_open() and self._panel.kind == HelpPanel.CENTERED:
            self._panel.raise_dim()
            self._panel.raise_()

    # --- Esc, whoever has the focus -----------------------------------------------------------------------------

    def eventFilter(self, obj, event):
        """The first Esc closes the help even when a pop-up of the window (the bookmark list, say) holds the focus and
        would take the key itself. (A name being typed, the settings panel and other windows keep their Esc.)"""
        if (event.type() == QEvent.KeyPress and event.key() == Qt.Key_Escape and self.is_open()
                and isinstance(obj, QWidget) and obj.window() is self.window):
            bookmark_panel = self.window.bookmark_panel
            if self.window.controller.settings_panel is None and not (bookmark_panel is not None and bookmark_panel.is_editing):
                self.close()
                event.accept()
                return True
        return False
