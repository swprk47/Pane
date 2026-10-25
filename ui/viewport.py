"""The video area of the main window: the mpv picture, the start screen over it while nothing is loaded, drag and drop of a
file, a drag anywhere moves the window, a click / double click / right click are reported as signals."""
import os

from PySide6.QtCore import Qt, QPoint, Signal
from PySide6.QtGui import QDragEnterEvent, QDropEvent, QMouseEvent
from PySide6.QtWidgets import QApplication

from ui.mpv_gl import MpvGLWidget
from ui.start_screen import StartScreen
from ui.title_bar import native_start_window_drag


class VideoViewport(MpvGLWidget):
    """
    Dedicated video rendering viewport.
    Supports dragging anywhere on the screen to move the window,
    right-click context menu, and file drag-and-drop.
    """
    file_dropped = Signal(str)
    double_clicked = Signal()
    clicked = Signal()
    context_menu_requested = Signal(QPoint)

    def __init__(self, parent_window):
        super().__init__(parent_window)
        self.parent_window = parent_window
        self.setAcceptDrops(True)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.NoFocus)
        self._press_pos = None
        self._drag_started = False
        self._after_double_click = False

        # Empty state: the start screen covers the viewport until a video is loaded
        self.start_screen = StartScreen(self)
        self.notice_widget = self.start_screen          # (what "is the empty state showing" asks)
        self.start_screen.setGeometry(self.rect())
        self.start_screen.show()

    def show_empty_notice(self, show: bool):
        self.start_screen.setVisible(show)
        if show:
            self.start_screen.raise_()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.start_screen.setGeometry(self.rect())

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            self.start_screen.set_dragging(True)
            event.acceptProposedAction()

    def dragLeaveEvent(self, event):
        self.start_screen.set_dragging(False)
        super().dragLeaveEvent(event)

    def dropEvent(self, event: QDropEvent):
        self.start_screen.set_dragging(False)
        urls = event.mimeData().urls()
        if urls:
            file_path = urls[0].toLocalFile()
            if os.path.exists(file_path):
                self.file_dropped.emit(file_path)
        event.acceptProposedAction()

    def mouseDoubleClickEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton:
            self._after_double_click = True
            self.double_clicked.emit()
            event.accept()

    def mousePressEvent(self, event: QMouseEvent):
        # Right button is deliberately not handled here: it falls through to
        # contextMenuEvent so the menu opens through exactly one code path.
        if event.button() == Qt.LeftButton:
            self._press_pos = event.position().toPoint()
            self._drag_started = False
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent):
        # Start the native window move only once the cursor really drags.
        # Starting it on press would swallow the button-up and break
        # click / double-click detection.
        if (event.buttons() & Qt.LeftButton and self._press_pos is not None
                and not self._drag_started
                and not self.parent_window.isFullScreen()
                and not self.parent_window.isMaximized()):
            moved = (event.position().toPoint() - self._press_pos).manhattanLength()
            if moved >= QApplication.startDragDistance():
                self._drag_started = True
                native_start_window_drag(int(self.parent_window.winId()))
                event.accept()
                return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton and self._press_pos is not None:
            if not self._drag_started and not self._after_double_click:
                self.clicked.emit()
            self._after_double_click = False
            self._press_pos = None
            event.accept()
        else:
            super().mouseReleaseEvent(event)

    def contextMenuEvent(self, event):
        self.context_menu_requested.emit(event.globalPos())
        event.accept()
