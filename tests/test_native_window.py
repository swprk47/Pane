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


# --- the sizing borders (WM_NCHITTEST) --------------------------------------------------------

RECT = (100, 80, 1100, 680)
B, C = 6, 14


@pytest.mark.parametrize("x, y, expected", [
    (101, 300, nw.HTLEFT), (1098, 300, nw.HTRIGHT), (500, 81, nw.HTTOP), (500, 678, nw.HTBOTTOM),
    (101, 81, nw.HTTOPLEFT), (1098, 81, nw.HTTOPRIGHT),
    (101, 678, nw.HTBOTTOMLEFT), (1098, 678, nw.HTBOTTOMRIGHT),
    (1090, 668, nw.HTBOTTOMRIGHT), (110, 668, nw.HTBOTTOMLEFT),         # (the bottom corners are bigger than the border)
    (500, 300, None), (110, 300, None), (500, 100, None),                # inside
    (50, 300, None), (1100, 300, None), (500, 680, None),                # outside
])
def test_resize_hit(x, y, expected):
    assert nw.resize_hit(x, y, RECT, B, C) == expected


def test_the_top_corners_are_not_bigger_than_the_border():
    """The title bar's buttons sit just below the top edge, at the right: a big corner would eat their clicks."""
    assert nw.resize_hit(1090, 90, RECT, B, C) is None
    assert nw.resize_hit(110, 90, RECT, B, C) is None


def _hit_test(hwnd, x, y):
    lparam = (x & 0xFFFF) | ((y & 0xFFFF) << 16)
    u = ctypes.windll.user32
    u.SendMessageW.restype = ctypes.c_ssize_t
    u.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    return int(u.SendMessageW(hwnd, nw.WM_NCHITTEST, 0, lparam))


def _window_rect(hwnd):
    r = wintypes.RECT()
    ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(r))
    return r.left, r.top, r.right, r.bottom


def test_windows_is_told_about_the_borders_of_the_real_window(window, pump):
    hwnd = int(window.winId())
    left, top, right, bottom = _window_rect(hwnd)
    mid_x, mid_y = (left + right) // 2, (top + bottom) // 2
    assert _hit_test(hwnd, right - 2, mid_y) == nw.HTRIGHT
    assert _hit_test(hwnd, left + 2, mid_y) == nw.HTLEFT
    assert _hit_test(hwnd, mid_x, bottom - 2) == nw.HTBOTTOM
    assert _hit_test(hwnd, right - 2, bottom - 2) == nw.HTBOTTOMRIGHT
    assert _hit_test(hwnd, left + 2, bottom - 2) == nw.HTBOTTOMLEFT
    assert _hit_test(hwnd, mid_x, top + 2) == nw.HTTOP
    assert _hit_test(hwnd, mid_x, mid_y) == nw.HTCLIENT


def test_no_sizing_borders_when_maximized_or_fullscreen(window, pump):
    hwnd = int(window.winId())
    window.title_bar._toggle_maximize()
    pump(timeout=0.6)
    left, top, right, bottom = _window_rect(hwnd)
    assert _hit_test(hwnd, right - 2, (top + bottom) // 2) == nw.HTCLIENT
    window.title_bar._toggle_maximize()
    pump(timeout=0.4)
    window.toggle_fullscreen()
    pump(timeout=0.6)
    left, top, right, bottom = _window_rect(hwnd)
    assert _hit_test(hwnd, right - 2, (top + bottom) // 2) == nw.HTCLIENT
    window.toggle_fullscreen()
    pump(timeout=0.4)


class MINMAXINFO(ctypes.Structure):
    _fields_ = [("ptReserved", wintypes.POINT), ("ptMaxSize", wintypes.POINT), ("ptMaxPosition", wintypes.POINT),
                ("ptMinTrackSize", wintypes.POINT), ("ptMaxTrackSize", wintypes.POINT)]


def test_windows_resizes_within_the_windows_minimum_size(window, pump):
    """Windows runs the resizing now; it asks the window for its limits (WM_GETMINMAXINFO), which Qt answers."""
    hwnd = int(window.winId())
    info = MINMAXINFO()
    u = ctypes.windll.user32
    u.SendMessageW.restype = ctypes.c_ssize_t
    u.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, ctypes.c_void_p]
    u.SendMessageW(hwnd, 0x0024, 0, ctypes.addressof(info))                 # WM_GETMINMAXINFO
    assert (info.ptMinTrackSize.x, info.ptMinTrackSize.y) == (window.minimumWidth(), window.minimumHeight()) == (640, 380)
