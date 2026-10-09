"""Windows' own window behaviour for the frameless window: snapping styles, no visible frame, maximizing."""
import ctypes
import sys
from ctypes import wintypes

import pytest

from ui import native_window as nw

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows only")


# --- the pure part -----------------------------------------------------------------------------

def test_a_normal_window_keeps_its_whole_rectangle_as_the_client_area():
    assert nw.client_rect((100, 80, 1100, 680), False, (0, 0, 2560, 1392)) == (100, 80, 1100, 680)


def test_a_maximized_window_is_cut_to_the_work_area():
    work = (0, 0, 2560, 1392)
    assert nw.client_rect((-8, -8, 2568, 1400), True, work) == (0, 0, 2560, 1392)      # hung outside: pulled in
    assert nw.client_rect((0, 0, 2560, 1392), True, work) == (0, 0, 2560, 1392), "one that already fits is left alone"


def test_no_work_area_means_no_cut():
    assert nw.client_rect((-8, -8, 2568, 1400), True, None) == (-8, -8, 2568, 1400)


def _message(msg_id, wparam=0, lparam=0):
    m = nw.MSG()
    m.message, m.wParam, m.lParam = msg_id, wparam, lparam
    return m


def test_unknown_messages_are_left_to_qt():
    m = _message(0x0200)                                       # WM_MOUSEMOVE
    assert nw.handle_message(ctypes.addressof(m)) is None


def test_nccalcsize_keeps_the_whole_window_as_the_client_area():
    params = nw.NCCALCSIZE_PARAMS()
    params.rgrc[0].left, params.rgrc[0].top, params.rgrc[0].right, params.rgrc[0].bottom = 100, 80, 1100, 680
    m = _message(nw.WM_NCCALCSIZE, 1, ctypes.addressof(params))
    m.hwnd = None
    assert nw.handle_message(ctypes.addressof(m)) == 0
    r = params.rgrc[0]
    assert (r.left, r.top, r.right, r.bottom) == (100, 80, 1100, 680)       # (not zoomed: untouched)


# --- on the real window -------------------------------------------------------------------------

def _client_rect_on_screen(hwnd):
    cr, pt = wintypes.RECT(), wintypes.POINT(0, 0)
    ctypes.windll.user32.GetClientRect(hwnd, ctypes.byref(cr))
    ctypes.windll.user32.ClientToScreen(hwnd, ctypes.byref(pt))
    return pt.x, pt.y, cr.right, cr.bottom


def test_the_window_has_the_styles_windows_needs_to_snap_and_resize_it(window):
    assert nw.has_native_frame(int(window.winId()))


def test_the_styles_survive_maximizing_and_fullscreen(window, pump):
    hwnd = int(window.winId())
    window.toggle_fullscreen()
    pump(timeout=0.5)
    assert nw.has_native_frame(hwnd)
    window.toggle_fullscreen()
    pump(timeout=0.5)
    assert nw.has_native_frame(hwnd)
    window.title_bar._toggle_maximize()
    pump(timeout=0.5)
    assert nw.has_native_frame(hwnd)
    window.title_bar._toggle_maximize()
    pump(timeout=0.3)


def test_enabling_it_again_changes_nothing(window):
    assert nw.enable_native_frame(int(window.winId())) is False


def test_no_visible_frame_the_client_area_is_the_whole_window(window, pump):
    hwnd = int(window.winId())
    wr = wintypes.RECT()
    ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(wr))
    x, y, w, h = _client_rect_on_screen(hwnd)
    assert (x, y, w, h) == (wr.left, wr.top, wr.right - wr.left, wr.bottom - wr.top)


def test_maximized_it_fills_exactly_the_work_area_without_bands(window, pump, qapp):
    """A fixed frame width taken off a maximized window left 8 px bands of desktop around the video."""
    window.title_bar._toggle_maximize()
    pump(timeout=0.6)
    hwnd = int(window.winId())
    assert window.isMaximized()
    x, y, w, h = _client_rect_on_screen(hwnd)
    work = window.screen().availableGeometry()
    assert (x, y, w, h) == (work.x(), work.y(), work.width(), work.height())
    window.title_bar._toggle_maximize()
    pump(timeout=0.3)


def test_maximizing_the_way_win_up_does_updates_the_title_button(window, pump):
    """Win+Up / a snap maximizes through Windows, not through the title bar's button."""
    hwnd = int(window.winId())
    assert window.title_bar.shows_restore is False
    ctypes.windll.user32.ShowWindow(hwnd, 3)                   # SW_MAXIMIZE
    pump(lambda: window.isMaximized(), timeout=2.0)
    assert window.isMaximized() and window.title_bar.shows_restore is True
    ctypes.windll.user32.ShowWindow(hwnd, 9)                   # SW_RESTORE
    pump(lambda: not window.isMaximized(), timeout=2.0)
    assert window.title_bar.shows_restore is False
