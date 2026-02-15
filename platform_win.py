import logging
from typing import Optional


def get_hwnd(widget) -> Optional[int]:
    """Return native window handle (HWND) for a Qt widget, or None."""
    try:
        if widget is None:
            return None
        hwnd = int(widget.winId())
        return hwnd
    except Exception:
        logging.exception("get_hwnd failed")
        return None


def set_window_topmost(hwnd: int) -> bool:
    """Make a native window topmost. Returns True on success."""
    try:
        import ctypes

        SWP_NOSIZE = 0x0001
        SWP_NOMOVE = 0x0002
        SWP_SHOWWINDOW = 0x0040
        HWND_TOPMOST = -1
        user32 = ctypes.windll.user32
        user32.SetWindowPos(
            hwnd,
            HWND_TOPMOST,
            0,
            0,
            0,
            0,
            SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW,
        )
        return True
    except Exception:
        logging.exception("set_window_topmost failed")
        return False


def set_exclude_from_capture(hwnd: int, exclude: bool = True) -> bool:
    """Set DWM attribute DWMWA_EXCLUDED_FROM_CAPTURE (17).

    This toggles whether the given window should be excluded from screen
    capture by the OS compositor.
    """
    try:
        import ctypes

        dwm = ctypes.windll.dwmapi
        DWMWA_EXCLUDED_FROM_CAPTURE = 17
        val = ctypes.c_int(1 if exclude else 0)
        dwm.DwmSetWindowAttribute(
            hwnd, DWMWA_EXCLUDED_FROM_CAPTURE, ctypes.byref(val), ctypes.sizeof(val)
        )
        return True
    except Exception:
        logging.exception("set_exclude_from_capture failed")
        return False


def try_set_display_affinity(hwnd: int) -> bool:
    """Try to set SetWindowDisplayAffinity as a best-effort fallback.

    Failures are ignored but logged.
    """
    try:
        import ctypes

        user32 = ctypes.windll.user32
        WDA_EXCLUDEFROMCAPTURE = 0x11
        user32.SetWindowDisplayAffinity(hwnd, WDA_EXCLUDEFROMCAPTURE)
        return True
    except Exception:
        logging.exception("try_set_display_affinity failed")
        return False
