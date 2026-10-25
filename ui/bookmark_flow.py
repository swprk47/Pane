"""Bookmarks and chapter marks of the loaded video, and what the window does with them: add, jump, rename, delete, the list
panel, the pins and gaps on the seek bar, and what the hover pill says over a pin or a chapter. The window forwards the old
names (`bookmarks`, `chapters`, `chapters_on`, `bookmark_panel`, `add_bookmark`, `jump_bookmark`, ...)."""
from PySide6.QtCore import QObject

from core import bookmarks as bookmark_logic
from core.media_info import format_clock
from ui.bookmark_panel import BookmarkPanel
from ui.timeline_slider import PIN_COLOR


class BookmarkFlow(QObject):
    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.bookmarks = []                              # the loaded video's bookmarks [{"t", "name"}]
        self.chapters = []                               # its chapters [(start, title)]
        self.chapters_on = window.app_settings.get_chapters_visible()
        self.panel = None                                # made on first use

    # --- state --------------------------------------------------------------------------------------------------

    def usable(self) -> bool:
        window = self.window
        return window._current_file is not None and window._duration > 0

    def forget(self):
        self.bookmarks, self.chapters = [], []
        if self.panel is not None:
            self.panel.hide()
        self.refresh()

    def open_video(self, path: str):
        """A video is being opened: the old one's marks go, this one's stored bookmarks come (its chapters come later,
        when mpv has loaded the file)."""
        self.forget()
        self.bookmarks = self.window.app_settings.get_bookmarks(path)
        self.refresh()

    def load_chapters(self):
        """(Once per video, when mpv has loaded the file.) The file's own chapters for the bar and the pill."""
        window = self.window
        self.chapters = window.engine.chapters() if window._current_file else []
        self.refresh()

    def refresh(self):
        """The pins and the chapter gaps into the seek bar, and the list into the panel when it is open."""
        window = self.window
        tl = window.controller.timeline
        tl.set_chapters_visible(self.chapters_on)
        tl.set_marks([b["t"] for b in self.bookmarks], [t for t, _title in self.chapters])
        panel = self.panel
        if panel is not None and panel.isVisible() and not panel.is_editing:      # (a name being typed is left alone)
            panel.set_items(self.bookmarks, window._duration)

    def set_bookmarks(self, items: list):
        self.bookmarks = items
        if self.window._current_file:
            self.window.app_settings.save_bookmarks(self.window._current_file, items)
        self.refresh()

    def on_chapters_changed(self, enabled: bool):
        self.chapters_on = enabled
        self.window.app_settings.set_chapters_visible(enabled)
        self.refresh()
        self.window.tips.hide()

    # --- actions ------------------------------------------------------------------------------------------------

    def add(self):
        window = self.window
        if not self.usable():
            return
        t = min(window._time_pos, window._duration)
        items, added, existing = bookmark_logic.add(self.bookmarks, t)
        if added:
            self.set_bookmarks(items)
            window.osd.show_message("북마크", "bookmark", format_clock(t))
        elif existing is not None:
            window.osd.show_message("이미 북마크가 있어요", "bookmark", format_clock(existing))
        else:
            window.osd.show_message(f"북마크는 영상마다 {bookmark_logic.MAX_PER_VIDEO}개까지 저장돼요", "warning")

    def rename(self, t: float, name: str):
        self.set_bookmarks(bookmark_logic.rename(self.bookmarks, t, name))

    def delete(self, t: float):
        self.set_bookmarks(bookmark_logic.remove(self.bookmarks, t))

    def seek_to(self, t: float, say: bool):
        """An exact seek (the position is noted at once, so a quick second key press goes on from here)."""
        window = self.window
        window.next_up.cancel()
        window._time_pos = t
        window.engine.seek(t, reference="exact")
        if say:
            window.osd.show_message("북마크", "bookmark", format_clock(t))

    def jump(self, direction: int):
        """Alt+Right (+1) / Alt+Left (-1): the next / previous bookmark (one beyond the video's length is skipped)."""
        window = self.window
        if not self.usable():
            return
        usable = [b for b in self.bookmarks if b["t"] <= window._duration]
        target = (bookmark_logic.next_after(usable, window._time_pos) if direction > 0
                  else bookmark_logic.previous(usable, window._time_pos))
        if target is None:
            window.osd.show_message("다음 북마크가 없어요" if direction > 0 else "이전 북마크가 없어요", "warning")
        else:
            self.seek_to(target, say=True)

    # --- the list panel -----------------------------------------------------------------------------------------

    def toggle_panel(self):
        window = self.window
        if not self.usable():
            return
        if self.panel is None:
            panel = BookmarkPanel(window.central_widget)
            panel.opened.connect(lambda: panel.set_items(self.bookmarks, window._duration))
            panel.jump_requested.connect(lambda t: self.seek_to(t, say=False))
            panel.add_requested.connect(self.add)
            panel.rename_requested.connect(self.rename)
            panel.delete_requested.connect(self.delete)
            self.panel = panel
        button = window.controller.btn_bookmarks
        if button is None or not button.isVisible():
            button = window.controller.timeline
        self.panel.toggle_above_widget(button, align_to=window.controller.right_zone, above=window.controller.timeline)

    def panel_visible(self) -> bool:
        return self.panel is not None and self.panel.isVisible()

    def hide_panel(self):
        if self.panel is not None:
            self.panel.hide()

    def raise_panel(self):
        if self.panel is not None:
            self.panel.raise_()

    # --- the hover pill ---------------------------------------------------------------------------------------

    def pill_for(self, seconds: float, x: float):
        """(text, dot, detail) of the pill over the seek bar at `x` (a pixel in the bar), `seconds` being the time there:
        a bookmark under the pointer first, else the chapter, else the time."""
        text, dot, detail = format_clock(seconds), None, ""
        pin = self.window.controller.timeline.pin_at(x)
        item = next((b for b in self.bookmarks if b["t"] == pin), None) if pin is not None else None
        chapter = bookmark_logic.chapter_at(self.chapters, seconds) if self.chapters_on else None
        if item is not None:
            text, dot = bookmark_logic.display_name(item), PIN_COLOR
            detail = format_clock(item["t"]) if item["name"] else ""
        elif chapter is not None:
            text, detail = chapter[1], format_clock(seconds)
        return text, dot, detail
