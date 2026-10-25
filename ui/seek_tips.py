"""What shows above the seek bar while the pointer is over it: the time pill (or a bookmark's / a chapter's name) and, a
moment later, the picture of that moment. Owns the two tips, the thumbnail maker, the "only when the pointer rests" timer and
the two thumbnail switches; the window forwards the old names (`seek_tip`, `thumbnail_tip`, `thumbnail_provider`,
`thumbnails_on`, `thumbnails_on_stop`, `_hide_seek_tips`, `_on_thumbnails_changed`, `_on_thumbnails_on_stop_changed`)."""
from PySide6.QtCore import QObject, QPoint, QRect, QTimer

from core import bookmarks as bookmark_logic
from core.media_info import format_clock
from core.thumbnails import ThumbnailProvider, bucket_of
from ui.overlay import SeekTimeTip, ThumbnailTip
from ui.timeline_slider import PIN_COLOR


class SeekTips(QObject):
    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.seek_tip = SeekTimeTip(window.central_widget)
        self.thumbnail_tip = ThumbnailTip(window.central_widget)
        self.thumbnail_provider = ThumbnailProvider(window)
        self.thumbnail_provider.thumbnail_ready.connect(self.on_ready)
        self._spot = None                                # (seconds, x) of the pointer while it is over the seek bar
        self._viewport = None                            # the video area the pill and the picture were placed in
        self._stop_timer = QTimer(self)                  # "only when the pointer rests": fires STOP_DELAY_MS after the last move
        self._stop_timer.setSingleShot(True)
        self._stop_timer.timeout.connect(self.request)
        self.thumbnails_on = window.app_settings.get_thumbnails_enabled()
        self.thumbnails_on_stop = window.app_settings.get_thumbnails_on_stop()
        self.thumbnail_provider.set_enabled(self.thumbnails_on)

    def show(self, seconds: float, x: float):
        """The time under the pointer, as a pill just above the seek bar."""
        window = self.window
        tl = window.controller.timeline
        spot = tl.mapTo(window.central_widget, QPoint(round(x), tl.height() // 2))
        text, dot, detail = format_clock(seconds), None, ""         # (a bookmark under the pointer, else its chapter, else the time)
        pin = tl.pin_at(x)
        item = next((b for b in window.bookmarks if b["t"] == pin), None) if pin is not None else None
        chapter = bookmark_logic.chapter_at(window.chapters, seconds) if window.chapters_on else None
        if item is not None:
            text, dot = bookmark_logic.display_name(item), PIN_COLOR
            detail = format_clock(item["t"]) if item["name"] else ""
        elif chapter is not None:
            text, detail = chapter[1], format_clock(seconds)
        self.seek_tip.show_at(text, spot.x(), spot.y() - 15, window.viewport.geometry(), dot=dot, detail=detail)
        self._spot = (seconds, spot.x())
        if not self._wanted():
            self.thumbnail_tip.hide_tip()
        elif self.thumbnails_on_stop:
            self.thumbnail_tip.hide_tip()                # moving: the time only; the picture comes when the pointer rests
            self._stop_timer.start(window.STOP_DELAY_MS)
        else:
            self.request()

    def _wanted(self) -> bool:
        window = self.window
        return bool(self.thumbnails_on and window._current_file is not None and window._duration > 0)

    def _seconds(self) -> float:
        """The moment the picture is for: the time under the pointer, but never the very end (a seek to the end of a file
        that is kept open is the riskiest one): at most the last second."""
        return min(self._spot[0], max(0.0, self.window._duration - 1.0))

    def request(self):
        if self._spot is not None and self._wanted():
            self.thumbnail_provider.request(self.window._current_file, self._seconds())

    def on_ready(self, path: str, bucket: int, image):
        """A picture arrived: shown only for the file and the 2 s step the pointer is at now (a late one is dropped)."""
        window = self.window
        spot = self._spot
        if (spot is None or path != window._current_file or bucket != bucket_of(self._seconds())
                or not self.seek_tip.isVisible() or not self._wanted()
                or (self.thumbnails_on_stop and self._stop_timer.isActive())):
            return
        self.thumbnail_tip.show_at(image, spot[1], self.seek_tip.y() - ThumbnailTip.GAP, window.viewport.geometry())

    def hide(self):
        """The pill and the picture go together; nothing is asked for any more."""
        self.seek_tip.hide_tip()
        self.thumbnail_tip.hide_tip()
        self._stop_timer.stop()
        self._spot = None

    def on_thumbnails_changed(self, enabled: bool):
        self.thumbnails_on = enabled
        self.window.app_settings.set_thumbnails_enabled(enabled)
        self.thumbnail_provider.set_enabled(enabled)
        if not enabled:
            self._stop_timer.stop()
            self.thumbnail_tip.hide_tip()

    def on_thumbnails_on_stop_changed(self, enabled: bool):
        self.thumbnails_on_stop = enabled
        self.window.app_settings.set_thumbnails_on_stop(enabled)
        self._stop_timer.stop()
        self.thumbnail_tip.hide_tip()

    def area_changed(self, viewport_rect: QRect) -> bool:
        """The window lays its overlays out for `viewport_rect`: True (and the tips are hidden) when that area is not the one
        the tips were placed for; a layout pass that changes nothing leaves them alone."""
        if viewport_rect == self._viewport:
            return False
        self._viewport = QRect(viewport_rect)
        self.hide()
        return True

    def shutdown(self):
        self.thumbnail_provider.shutdown()               # (a picture in the making gets a second at most)
