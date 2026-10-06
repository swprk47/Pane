"""
Real Windows mouse input (SetCursorPos / mouse_event). These move the cursor and
need the window on screen, so they are skipped unless you ask for them:

    pytest --run-e2e        (or PANE_E2E=1)

Covers what unit tests cannot: clicks falling through the translucent window to
the desktop, and the right-click / double-click / drag / click-to-pause paths.
"""
import ctypes
import time
from ctypes import wintypes

import pytest
from PySide6.QtCore import QPoint

import ui.main_window as mw

pytestmark = pytest.mark.e2e

user32 = ctypes.windll.user32
user32.WindowFromPoint.argtypes = [wintypes.POINT]
user32.WindowFromPoint.restype = wintypes.HWND
user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
user32.GetAncestor.restype = wintypes.HWND

HWND_TOPMOST, SWP_NOSIZE, SWP_NOMOVE, SWP_SHOWWINDOW = -1, 0x1, 0x2, 0x40
LEFT_DOWN, LEFT_UP, RIGHT_DOWN, RIGHT_UP, MOVE = 0x2, 0x4, 0x8, 0x10, 0x1


@pytest.fixture
def screen_window(window, pump, monkeypatch):
    window.move(100, 100)
    window.resize(1000, 600)
    user32.SetWindowPos(int(window.winId()), HWND_TOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW)
    pump(timeout=0.4)
    started = []
    # entering the system move loop would block the test
    monkeypatch.setattr(mw, "native_start_window_drag", lambda hwnd: started.append(hwnd) or True)
    window._drag_calls = started
    return window


class Mouse:
    def __init__(self, pump):
        self.pump = pump

    def click(self, x, y, right=False, times=1):
        user32.SetCursorPos(int(x), int(y))
        self.pump(timeout=0.08)
        down, up = (RIGHT_DOWN, RIGHT_UP) if right else (LEFT_DOWN, LEFT_UP)
        for _ in range(times):
            user32.mouse_event(down, 0, 0, 0, 0)
            self.pump(timeout=0.02)
            user32.mouse_event(up, 0, 0, 0, 0)
            self.pump(timeout=0.09)

    def drag(self, x, y, dx=32):
        user32.SetCursorPos(int(x), int(y))
        self.pump(timeout=0.08)
        user32.mouse_event(LEFT_DOWN, 0, 0, 0, 0)
        self.pump(timeout=0.02)
        for _ in range(dx // 8):
            user32.mouse_event(MOVE, 8, 0, 0, 0)
            self.pump(timeout=0.02)
        user32.mouse_event(LEFT_UP, 0, 0, 0, 0)
        self.pump(timeout=0.1)


@pytest.fixture
def mouse(pump):
    return Mouse(pump)


def hit_test_grid(window):
    """Fraction of sample points inside the window that Windows hands to Pane itself."""
    top = int(window.winId())
    g = window.geometry()
    inside = total = 0
    for fy in (0.03, 0.1, 0.3, 0.5, 0.7, 0.9, 0.97):
        for fx in (0.03, 0.2, 0.5, 0.8, 0.97):
            pt = wintypes.POINT(g.x() + int(g.width() * fx), g.y() + int(g.height() * fy))
            h = user32.WindowFromPoint(pt) or 0
            total += 1
            if h == top or user32.GetAncestor(h, 2) == top:
                inside += 1
    return inside, total


def test_no_click_through_to_the_desktop_when_empty(screen_window):
    inside, total = hit_test_grid(screen_window)
    assert inside == total, f"{total - inside} points fall through to windows behind Pane"


def test_no_click_through_while_playing(screen_window, sample_video, pump):
    screen_window.load_media_file(sample_video)
    pump(timeout=1.0)
    inside, total = hit_test_grid(screen_window)
    assert inside == total


def _video_point(window, fy=0.25):
    vp = window.viewport
    return vp.mapToGlobal(QPoint(vp.width() // 2, int(vp.height() * fy)))


def _scrim_point(window):
    c = window.controller
    return c.mapToGlobal(QPoint(c.width() // 2 + 90, 40))             # empty part of the gradient


@pytest.mark.parametrize("where", ["video", "scrim"])
def test_right_click_double_click_and_drag(screen_window, sample_video, pump, mouse, where):
    w = screen_window
    w.load_media_file(sample_video)
    w.engine.mpv.loop_file = "inf"
    pump(timeout=1.0)
    events = []
    w.viewport.context_menu_requested.disconnect()
    w.viewport.double_clicked.disconnect()
    w.viewport.context_menu_requested.connect(lambda p: events.append("context"))
    w.viewport.double_clicked.connect(lambda: events.append("double"))
    p = _video_point(w) if where == "video" else _scrim_point(w)

    mouse.click(p.x(), p.y(), right=True)
    pump(timeout=0.2)
    assert events == ["context"]

    events.clear()
    mouse.click(p.x(), p.y(), times=2)
    pump(timeout=0.3)
    assert events == ["double"]

    w._drag_calls.clear()
    mouse.drag(p.x(), p.y())
    assert len(w._drag_calls) == 1


def test_click_toggles_pause_but_drag_does_not(screen_window, sample_video, pump, mouse):
    w = screen_window
    w.load_media_file(sample_video)
    w.engine.mpv.loop_file = "inf"
    pump(lambda: w.engine._time_pos > 0.2)
    p = _video_point(w)

    mouse.click(p.x(), p.y())
    assert pump(lambda: not w.engine.is_playing(), timeout=1.0)
    # Two clicks closer together than the system double-click time (500 ms) are a
    # double-click (fullscreen), so wait it out.
    pump(timeout=user32.GetDoubleClickTime() / 1000 + 0.2)
    mouse.click(p.x(), p.y())
    assert pump(lambda: w.engine.is_playing(), timeout=1.0)

    # A press within the double-click time of the last click IS a double-click (and undoes that click's
    # toggle), so let that time pass before testing a plain drag.
    pump(timeout=user32.GetDoubleClickTime() / 1000 + 0.2)
    before = w.engine.is_playing()
    mouse.drag(p.x(), p.y())
    pump(timeout=0.5)
    assert w.engine.is_playing() == before


def test_double_click_does_not_pause(screen_window, sample_video, pump, mouse):
    w = screen_window
    w.load_media_file(sample_video)
    w.engine.mpv.loop_file = "inf"
    pump(lambda: w.engine._time_pos > 0.2)
    p = _video_point(w)
    mouse.click(p.x(), p.y(), times=2)
    pump(timeout=0.7)
    assert w.isFullScreen() and w.engine.is_playing()
    w.toggle_fullscreen()


def test_volume_popup_opens_on_hover_and_closes_on_leave(screen_window, sample_video, pump):
    w = screen_window
    w.load_media_file(sample_video)
    pump(timeout=0.8)
    c = w.controller
    btn = c.btn_mute.mapToGlobal(c.btn_mute.rect().center())
    user32.SetCursorPos(btn.x() - 300, btn.y() - 200)
    pump(timeout=0.3)
    user32.SetCursorPos(btn.x(), btn.y())
    assert pump(lambda: c.volume_popup.isVisible(), timeout=1.0)
    user32.SetCursorPos(btn.x() - 500, btn.y() - 300)
    assert pump(lambda: not c.volume_popup.isVisible(), timeout=1.5)


def _title_spot(window):
    return window.title_bar.mapToGlobal(QPoint(window.title_bar.width() // 2, window.title_bar.height() // 2))


def test_title_bar_double_click_maximizes_and_restores(screen_window, pump, mouse, monkeypatch):
    import ui.title_bar as tb
    started = []
    monkeypatch.setattr(tb, "native_start_window_drag", lambda hwnd: started.append(hwnd) or True)
    w = screen_window
    p = _title_spot(w)
    mouse.click(p.x(), p.y(), times=2)
    pump(timeout=0.6)
    assert w.isMaximized() and started == []
    p = _title_spot(w)
    mouse.click(p.x(), p.y(), times=2)
    pump(timeout=0.6)
    assert not w.isMaximized()


def test_title_bar_drag_with_the_real_mouse(screen_window, pump, mouse, monkeypatch):
    import ui.title_bar as tb
    started = []
    monkeypatch.setattr(tb, "native_start_window_drag", lambda hwnd: started.append(hwnd) or True)
    p = _title_spot(screen_window)
    mouse.drag(p.x(), p.y())
    assert len(started) == 1
