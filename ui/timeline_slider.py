from PySide6.QtCore import QRect, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QMouseEvent, QPen

from core import bookmarks
from ui.glass_slider import GlassSlider


PREVIEW_COLOR = QColor(255, 255, 255, 110)      # the part from the handle to the pointer (only ahead of the handle)
MARKER_COLOR = QColor(255, 255, 255, 245)       # its end: as thick as the (hovered) track, no taller
MARKER_WIDTH = 2.0
PIN_COLOR = QColor(255, 200, 87)                # a bookmark: a vertical amber pin across the bar
PIN_W, PIN_H = 4, 18
PIN_W_NEAR, PIN_H_NEAR = 5, 24                  # while the pointer is near it
PIN_OUTLINE = QColor(255, 255, 255, 230)
PIN_REACH = 6.0                                 # pixels: how near the pointer must be to a pin to hover or press it
GAP_WIDTH = 2.0                                 # a chapter gap at rest ... (+1 px while the bar is hovered)


class TimelineSlider(GlassSlider):
    """
    Glass-styled hover-responsive timeline seek bar (drawn by GlassSlider: thin track that thickens and a
    round white handle that grows on hover). Supports click-to-seek and drag-to-seek.
    """
    seek_requested = Signal(float)  # Requested position in seconds
    hover_moved = Signal(float, float)   # time under the pointer (or the one being dragged to), its x in this widget
    hover_left = Signal()                # the pointer left the bar (not while a drag goes on)
    pin_pressed = Signal(float)          # a press on a bookmark pin: the pin's time (the handle does not move)

    def __init__(self, parent=None):
        super().__init__(Qt.Horizontal, parent)
        self.setRange(0, 1000)
        self.setValue(0)
        self.setFixedHeight(26)         # room for the grown handle and its press halo

        self._duration = 0.0
        self._is_dragging = False
        self._hover_ratio = None         # where the pointer is on the bar (0..1) while it is over it, else None
        self._bookmarks = []             # seconds of the bookmarks of the loaded video
        self._chapters = []              # seconds of its chapter starts
        self._chapters_visible = True
        self._pin_click = False          # the press that is going on started on a pin

    def set_duration(self, duration: float):
        self._duration = max(0.0, float(duration))

    def set_marks(self, bookmark_times: list, chapter_times: list):
        """Bookmarks (pins) and chapter starts (gaps) of the loaded video, in seconds; empty lists draw nothing extra."""
        self._bookmarks = [float(t) for t in bookmark_times]
        self._chapters = [float(t) for t in chapter_times]
        self.update()

    def set_chapters_visible(self, visible: bool):
        self._chapters_visible = bool(visible)
        self.update()

    def _pin_marks(self) -> list:
        """[(time, pixel x)] of the bookmarks that lie inside the video."""
        if self._duration <= 0:
            return []
        m, span = self._margin(), self._span()
        return [(t, m + t / self._duration * span) for t in self._bookmarks if 0 <= t <= self._duration]

    def pin_at(self, x: float):
        """The time of the bookmark pin within PIN_REACH pixels of x (the nearest), else None."""
        return bookmarks.nearest(self._pin_marks(), x, PIN_REACH)

    def track_gaps(self, margin, span, cy, thickness):
        if not self._chapters_visible or not self._chapters or self._duration <= 0:
            return []
        width = int(GAP_WIDTH + self._hover + 0.5)
        top, height = int(cy - thickness / 2) - 1, int(thickness) + 3
        return [QRect(int(round(margin + r * span - width / 2.0)), top, width, height)
                for r in bookmarks.gap_ratios(self._chapters, self._duration, span)]

    def set_time_pos(self, time_pos: float):
        """Update slider position from playback progress (only when not dragging)."""
        if self._is_dragging or self._duration <= 0.0:
            return
        ratio = max(0.0, min(1.0, time_pos / self._duration))
        self.blockSignals(True)
        self.setValue(int(ratio * 1000))
        self.blockSignals(False)
        self.update()

    # --- hover preview --------------------------------------------------------------------------
    def _preview_ratio(self):
        if self._hover_ratio is None or self._is_dragging or self._duration <= 0:
            return None
        return self._hover_ratio

    def paint_over_track(self, p, margin, span, cy, thickness):
        h = self._preview_ratio()
        r = self.value_ratio()
        if h is not None and h > r:                 # (behind the handle what was played keeps its colour)
            x0, x1 = margin + r * span, margin + h * span
            p.setPen(Qt.NoPen)
            p.setBrush(PREVIEW_COLOR)
            p.drawRect(QRectF(x0, cy - thickness / 2, x1 - x0, thickness))
            p.setBrush(MARKER_COLOR)
            p.drawRoundedRect(QRectF(margin + h * span - MARKER_WIDTH / 2, cy - thickness / 2, MARKER_WIDTH, thickness),
                              MARKER_WIDTH / 2, MARKER_WIDTH / 2)
        self._paint_pins(p, margin, span, cy)

    def _paint_pins(self, p, margin, span, cy):
        pointer_x = None if self._hover_ratio is None or self._is_dragging else margin + self._hover_ratio * span
        for _t, x in self._pin_marks():
            near = pointer_x is not None and abs(pointer_x - x) <= PIN_REACH
            w, h = (PIN_W_NEAR, PIN_H_NEAR) if near else (PIN_W, PIN_H)
            rect = QRectF(x - w / 2.0, cy - h / 2.0, w, h)
            p.setBrush(PIN_COLOR)
            p.setPen(QPen(PIN_OUTLINE, 1.5) if near else Qt.NoPen)
            p.drawRoundedRect(rect, w / 2.0, w / 2.0)
        p.setPen(Qt.NoPen)

    def _report_hover(self, ratio: float):
        self._hover_ratio = ratio
        if self._duration > 0:
            self.hover_moved.emit(ratio * self._duration, self._margin() + ratio * self._span())
        self.update()

    def leaveEvent(self, event):
        self._hover_ratio = None
        if not self._is_dragging:
            self.hover_left.emit()
        self.update()
        super().leaveEvent(event)

    def hideEvent(self, event):
        self._hover_ratio = None
        self.hover_left.emit()
        super().hideEvent(event)

    def _emit_seek(self):
        if self._duration > 0:
            self.seek_requested.emit(self.value_ratio() * self._duration)

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton:
            pin = self.pin_at(event.position().x())
            if pin is not None:                      # a press on a bookmark pin: go there, do not grab the handle
                self._pin_click = True
                self.pin_pressed.emit(pin)
                event.accept()
                return
            self._is_dragging = True
            super().mousePressEvent(event)           # sets the value under the pointer
            self._emit_seek()
            self._report_hover(self.value_ratio())
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent):
        if self._is_dragging:
            super().mouseMoveEvent(event)
            self._emit_seek()
            self._report_hover(self.value_ratio())
        else:
            super().mouseMoveEvent(event)
            self._report_hover(self.ratio_from_pos(event.position()))

    def mouseReleaseEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton and self._pin_click:
            self._pin_click = False                  # (the release of a press that started on a pin)
            event.accept()
            return
        if event.button() == Qt.LeftButton:
            self._is_dragging = False
            self.setValue(self.value_from_pos(event.position()))
            self._emit_seek()
            super().mouseReleaseEvent(event)
            if not self.underMouse():
                self._hover_ratio = None
                self.hover_left.emit()
            self.update()
        else:
            super().mouseReleaseEvent(event)
