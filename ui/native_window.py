"""
Windows' own window behaviour for the frameless player window.

A window made with ``Qt.FramelessWindowHint`` has no sizing border and no "maximizable" style, so Windows treats it
as something that cannot be snapped or resized: Win+Left / Right / Up / Down do nothing, and the edges cannot be
dragged. The usual cure for a window that draws its own title bar is to give it those styles anyway and take the
visible frame away again:

  * ``WS_THICKFRAME | WS_MAXIMIZEBOX | WS_MINIMIZEBOX | WS_SYSMENU`` are added to the window style
    (``enable_native_frame``), which brings snapping, Win+arrow keys, the taskbar menu and Alt+Space;
  * ``WM_NCCALCSIZE`` is answered so that the client area is the whole window: no frame is drawn
    (``handle_message``). A maximized window is kept inside the monitor's work area: Windows places a window with a
    sizing frame a frame's width beyond the screen on every side (here Qt already fits it to the work area, so
    subtracting a fixed frame width left 8 px bands of desktop around the video).

  * ``WM_NCHITTEST`` tells Windows which strip along the edge is a sizing border (``resize_hit``): Windows then
    shows the resize cursors and runs the whole resize itself (minimum size included). The border is thin on the
    top, where the title bar's buttons sit just below it, and larger in the bottom corners.

Qt rewrites the window style when the flags or the fullscreen state change, so the window calls
``enable_native_frame`` again after those.
"""
import ctypes
import sys
from ctypes import wintypes

IS_WINDOWS = sys.platform == "win32"

GWL_STYLE = -16
WS_MAXIMIZEBOX = 0x00010000
WS_MINIMIZEBOX = 0x00020000
WS_THICKFRAME = 0x00040000
WS_SYSMENU = 0x00080000
NATIVE_FRAME_STYLES = WS_THICKFRAME | WS_MAXIMIZEBOX | WS_MINIMIZEBOX | WS_SYSMENU

SWP_NOSIZE, SWP_NOMOVE, SWP_NOZORDER, SWP_NOACTIVATE, SWP_FRAMECHANGED = 0x0001, 0x0002, 0x0004, 0x0010, 0x0020
WM_NCCALCSIZE = 0x0083
WM_NCHITTEST = 0x0084
HTCLIENT, HTLEFT, HTRIGHT, HTTOP, HTTOPLEFT, HTTOPRIGHT, HTBOTTOM, HTBOTTOMLEFT, HTBOTTOMRIGHT = 1, 10, 11, 12, 13, 14, 15, 16, 17
RESIZE_BORDER = 6          # px at 100 % scale: the sizing strip along the left, right, top and bottom edges
RESIZE_CORNER = 14         # px: the bottom corners are easier to grab (the top ones are not: the title bar's buttons are there)


class RECT(ctypes.Structure):
    _fields_ = [("left", wintypes.LONG), ("top", wintypes.LONG), ("right", wintypes.LONG), ("bottom", wintypes.LONG)]


class NCCALCSIZE_PARAMS(ctypes.Structure):
    _fields_ = [("rgrc", RECT * 3), ("lppos", ctypes.c_void_p)]


class MSG(ctypes.Structure):
    _fields_ = [("hwnd", wintypes.HWND), ("message", wintypes.UINT), ("wParam", wintypes.WPARAM),
                ("lParam", wintypes.LPARAM), ("time", wintypes.DWORD), ("pt", wintypes.POINT)]


def _user32():
    u = ctypes.windll.user32
    u.GetWindowLongPtrW.restype = ctypes.c_ssize_t
    u.GetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int]
    u.SetWindowLongPtrW.restype = ctypes.c_ssize_t
    u.SetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]
    u.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.UINT]
    u.IsZoomed.argtypes = [wintypes.HWND]
    return u


def window_style(hwnd: int) -> int:
    return int(_user32().GetWindowLongPtrW(hwnd, GWL_STYLE)) & 0xFFFFFFFF


def has_native_frame(hwnd: int) -> bool:
    return (window_style(hwnd) & NATIVE_FRAME_STYLES) == NATIVE_FRAME_STYLES


def enable_native_frame(hwnd: int) -> bool:
    """Give the window the styles that make Windows treat it as a normal, snappable, resizable window. Safe to call
    again (it does nothing when the styles are already there). Returns whether anything was changed."""
    if not IS_WINDOWS or not hwnd:
        return False
    u = _user32()
    style = int(u.GetWindowLongPtrW(hwnd, GWL_STYLE))
    wanted = style | NATIVE_FRAME_STYLES
    if wanted == style:
        return False
    u.SetWindowLongPtrW(hwnd, GWL_STYLE, wanted)
    # tell Windows to look at the frame again (and answer WM_NCCALCSIZE for it)
    u.SetWindowPos(hwnd, None, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE | SWP_FRAMECHANGED)
    return True


def client_rect(window_rect, zoomed: bool, work_area):
    """The client area for a proposed window rectangle (left, top, right, bottom): all of it, except that a maximized
    window is cut to the monitor's work area (so a window hung outside the screen is pulled back in, and one that
    already fits is left alone)."""
    left, top, right, bottom = window_rect
    if zoomed and work_area is not None:
        wl, wt, wr, wb = work_area
        return max(left, wl), max(top, wt), min(right, wr), min(bottom, wb)
    return left, top, right, bottom


class MONITORINFO(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", RECT), ("rcWork", RECT), ("dwFlags", wintypes.DWORD)]


def _work_area(hwnd: int):
    u = ctypes.windll.user32
    u.MonitorFromWindow.restype = wintypes.HANDLE
    u.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
    u.GetMonitorInfoW.argtypes = [wintypes.HANDLE, ctypes.POINTER(MONITORINFO)]
    monitor = u.MonitorFromWindow(hwnd, 2)                          # MONITOR_DEFAULTTONEAREST
    info = MONITORINFO()
    info.cbSize = ctypes.sizeof(MONITORINFO)
    if not monitor or not u.GetMonitorInfoW(monitor, ctypes.byref(info)):
        return None
    w = info.rcWork
    return w.left, w.top, w.right, w.bottom


def resize_hit(x: int, y: int, rect, border: int, corner: int):
    """Which sizing border (an HT* code) the screen point (x, y) is on for a window `rect` = (left, top, right,
    bottom), or None when it is not on one."""
    left, top, right, bottom = rect
    if not (left <= x < right and top <= y < bottom):
        return None
    on_left, on_right = x - left < border, right - 1 - x < border
    on_top, on_bottom = y - top < border, bottom - 1 - y < border
    if on_top and on_left:
        return HTTOPLEFT
    if on_top and on_right:
        return HTTOPRIGHT
    if (on_bottom or bottom - 1 - y < corner) and (on_left or x - left < corner):
        return HTBOTTOMLEFT
    if (on_bottom or bottom - 1 - y < corner) and (on_right or right - 1 - x < corner):
        return HTBOTTOMRIGHT
    if on_left:
        return HTLEFT
    if on_right:
        return HTRIGHT
    if on_top:
        return HTTOP
    if on_bottom:
        return HTBOTTOM
    return None


def _dpi_scale(hwnd: int) -> float:
    u = ctypes.windll.user32
    u.GetDpiForWindow.argtypes = [wintypes.HWND]
    return (u.GetDpiForWindow(hwnd) or 96) / 96.0


def handle_message(msg_address: int, resizable: bool = True):
    """Answer the window messages that are ours. Returns the message result (an int) when handled, else None.
    (The window handle comes from the message: asking Qt for ``winId()`` from here would create the native window
    again from inside its own creation.)"""
    if not IS_WINDOWS:
        return None
    msg = MSG.from_address(msg_address)
    hwnd = msg.hwnd
    if msg.message == WM_NCHITTEST and resizable:
        x = ctypes.c_short(msg.lParam & 0xFFFF).value            # screen coordinates, signed 16 bit each
        y = ctypes.c_short((msg.lParam >> 16) & 0xFFFF).value
        rect = wintypes.RECT()
        ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rect))
        scale = _dpi_scale(hwnd)
        hit = resize_hit(x, y, (rect.left, rect.top, rect.right, rect.bottom),
                         round(RESIZE_BORDER * scale), round(RESIZE_CORNER * scale))
        return hit                                               # (None: Qt answers, i.e. the client area)
    if msg.message == WM_NCCALCSIZE:
        if msg.wParam:                                   # (wParam false: a plain rectangle; nothing to do)
            params = NCCALCSIZE_PARAMS.from_address(msg.lParam)
            rect = params.rgrc[0]
            zoomed = bool(_user32().IsZoomed(hwnd))
            rect.left, rect.top, rect.right, rect.bottom = client_rect(
                (rect.left, rect.top, rect.right, rect.bottom), zoomed, _work_area(hwnd) if zoomed else None)
        return 0
    return None
