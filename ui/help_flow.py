"""The shortcut help on the window: when it opens, which layout it takes, and what closes or re-places it. The panel itself is
``ui.help_panel.HelpPanel`` (made on the first open, then kept); the window only creates this and connects the title-bar
button, the key router (``?``, ``Esc``) and the right-click menu to it."""
from PySide6.QtCore import QObject

from ui.help_panel import HelpPanel

CENTERED_MIN = (720, 460)               # a video area at least this big (with no video loaded) gets the centred panel


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

    # --- opening and closing ------------------------------------------------------------------------------------

    def toggle(self):
        self.close() if self.is_open() else self.open()

    def open(self):
        window = self.window
        if self._panel is None:
            self._panel = HelpPanel(window.central_widget)
            self._panel.close_requested.connect(self.close)
        self._panel.show_as(self.layout_kind(), window.viewport.geometry())
        window._reposition_floating_widgets()           # (the stacking order)

    def close(self):
        if self._panel is not None:
            self._panel.hide_help()

    def relayout(self):
        """The window's size or mode changed: choose the layout again and place the panel."""
        if self.is_open():
            self._panel.show_as(self.layout_kind(), self.window.viewport.geometry())

    def raise_panel(self):
        if self.is_open():
            self._panel.raise_()
