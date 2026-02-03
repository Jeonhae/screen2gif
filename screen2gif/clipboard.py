"""Cross-platform clipboard helpers for screen2gif.

On Windows this delegates to clipboard_win functions (CF_HDROP/Ctypes/pywin32).
On other platforms it falls back to copying the file path as text via tkinter/pyperclip.
"""
import os
import sys


if sys.platform == "win32":
    try:
        from .clipboard_win import (
            copy_file_to_clipboard_cfhdrop_ctypes,
            copy_gif_to_clipboard_ctypes,
            copy_gif_to_clipboard_pywin32,
        )
    except Exception:
        # If import fails, provide safe fallbacks that return False
        def copy_file_to_clipboard_cfhdrop_ctypes(path: str) -> bool:  # type: ignore
            return False

        def copy_gif_to_clipboard_ctypes(path: str) -> bool:  # type: ignore
            return False

        def copy_gif_to_clipboard_pywin32(path: str) -> bool:  # type: ignore
            return False


    def copy_gif_to_clipboard(path: str) -> bool:
        # Prefer CF_HDROP file-object approach per SDD
        try:
            ok = copy_file_to_clipboard_cfhdrop_ctypes(path)
            if ok:
                return True
        except Exception:
            pass

        # Fallback to ctypes GIF custom format
        try:
            ok = copy_gif_to_clipboard_ctypes(path)
            if ok:
                return True
        except Exception:
            pass

        # Last attempt: pywin32 helper
        try:
            return copy_gif_to_clipboard_pywin32(path)
        except Exception:
            return False


    def copy_path_to_clipboard(path: str) -> bool:
        try:
            return copy_file_to_clipboard_cfhdrop_ctypes(path)
        except Exception:
            return False

else:
    def copy_gif_to_clipboard(path: str) -> bool:
        # Non-Windows: copy the absolute path as text to clipboard
        try:
            import tkinter as tk

            root = tk.Tk()
            root.withdraw()
            root.clipboard_clear()
            root.clipboard_append(os.path.abspath(path))
            root.update()
            root.destroy()
            return True
        except Exception:
            try:
                import pyperclip

                pyperclip.copy(os.path.abspath(path))
                return True
            except Exception:
                return False


    copy_path_to_clipboard = copy_gif_to_clipboard
import sys
import os

if sys.platform == 'win32':
    from . import clipboard_win as _cw

    def copy_gif_to_clipboard(path: str) -> bool:
        # Use CF_HDROP file-object approach per SDD
        try:
            return _cw.copy_file_to_clipboard_cfhdrop_ctypes(path)
        except Exception:
            return False

    def copy_path_to_clipboard(path: str) -> bool:
        # fallback to putting path text
        try:
            return _cw.copy_gif_to_clipboard_ctypes(path)
        except Exception:
            return False
else:
    # Non-windows simple fallback
    def copy_gif_to_clipboard(path: str) -> bool:
        try:
            import tkinter as tk
            root = tk.Tk()
            root.withdraw()
            root.clipboard_clear()
            root.clipboard_append(os.path.abspath(path))
            root.update()
            root.destroy()
            return True
        except Exception:
            try:
                import pyperclip
                pyperclip.copy(os.path.abspath(path))
                return True
            except Exception:
                return False

    copy_path_to_clipboard = copy_gif_to_clipboard
"""
Clean, robust clipboard helpers and logging.
"""

import os
import sys
import io
import ctypes
import struct
import traceback
from datetime import datetime
from typing import Optional
from PIL import Image


def _log(msg: str) -> None:
    try:
        base = os.path.dirname(__file__)
        logdir = os.path.join(base, 'logs')
        os.makedirs(logdir, exist_ok=True)
        path = os.path.join(logdir, 'clipboard_debug.log')
        with open(path, 'a', encoding='utf-8') as f:
            f.write(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}\n")
    except Exception:
        pass


def _log_win_error(prefix: str, kernel32) -> None:
    try:
        err = kernel32.GetLastError()
    except Exception:
        err = None
    _log(f"{prefix}; GetLastError={err}")


def copy_path_to_clipboard(path: str) -> bool:
    try:
        import tkinter as tk
        root = tk.Tk()
        root.withdraw()
        root.clipboard_clear()
        root.clipboard_append(os.path.abspath(path))
        root.update()
        root.destroy()
        return True
    except Exception:
        try:
            import pyperclip
            pyperclip.copy(os.path.abspath(path))
            return True
        except Exception:
            _log('copy_path_to_clipboard failed:\n' + traceback.format_exc())
            return False


def _set_clipboard_data_win(format_id: int, data: bytes) -> bool:
    kernel32 = ctypes.windll.kernel32
    user32 = ctypes.windll.user32
    GMEM_MOVEABLE = 0x0002
    GMEM_ZEROINIT = 0x0040
    flags = GMEM_MOVEABLE | GMEM_ZEROINIT

    size = len(data)
    hGlobal = kernel32.GlobalAlloc(flags, size)
    if not hGlobal:
        _log('GlobalAlloc failed')
        return False
    lp = kernel32.GlobalLock(hGlobal)
    if not lp:
        kernel32.GlobalFree(hGlobal)
        _log('GlobalLock failed')
        return False
    # copy bytes into locked memory
    ctypes.memmove(lp, data, size)
    kernel32.GlobalUnlock(hGlobal)

    # Try opening clipboard with retries in case it's locked
    for attempt in range(5):
        if user32.OpenClipboard(0):
            break
        import time
        time.sleep(0.05)
    else:
        kernel32.GlobalFree(hGlobal)
        _log('OpenClipboard retries failed')
        return False

    try:
        user32.EmptyClipboard()
        if not user32.SetClipboardData(format_id, hGlobal):
            # SetClipboardData failed; free and return
            _log_win_error('SetClipboardData failed', kernel32)
            kernel32.GlobalFree(hGlobal)
            return False
        # On success, Windows owns the handle; do not free
        return True
    finally:
        user32.CloseClipboard()


def copy_gif_to_clipboard(gif_path: str) -> bool:
    """Try to copy the GIF binary to the Windows clipboard via ctypes.

    Returns True on success or best-effort fallback.
    """
    if sys.platform != 'win32':
        return False

    try:
        with open(gif_path, 'rb') as f:
            gif_data = f.read()
    except Exception:
        _log('copy_gif_to_clipboard: failed to read gif')
        return False

    user32 = ctypes.windll.user32
    # Try custom GIF format
    try:
        fmt = user32.RegisterClipboardFormatA(b'GIF')
        if fmt:
            ok = _set_clipboard_data_win(fmt, gif_data)
            if ok:
                _log('copy_gif_to_clipboard: wrote GIF custom format')
                return True
    except Exception:
        _log('copy_gif_to_clipboard: RegisterClipboardFormatA exception:\n' + traceback.format_exc())

    # Fallback: put first frame as CF_DIB and file path as CF_UNICODETEXT
    try:
        im = Image.open(gif_path)
        im.seek(0)
        bio = io.BytesIO()
        im.convert('RGB').save(bio, format='BMP')
        bmp = bio.getvalue()
        # BMP file has 14-byte BITMAPFILEHEADER; CF_DIB expects BITMAPINFOHEADER + data
        dib = bmp[14:]

        CF_DIB = 8
        CF_UNICODETEXT = 13

        # Put DIB
        if not _set_clipboard_data_win(CF_DIB, dib):
            _log('copy_gif_to_clipboard: CF_DIB write failed, falling back to path')
            copy_path_to_clipboard(gif_path)
            return False

        # Put file path as Unicode text
        path_text = os.path.abspath(gif_path).encode('utf-16le') + b'\x00\x00'
        if not _set_clipboard_data_win(CF_UNICODETEXT, path_text):
            _log('copy_gif_to_clipboard: CF_UNICODETEXT write failed')
        _log('copy_gif_to_clipboard: wrote CF_DIB and CF_UNICODETEXT')
        return True
    except Exception:
        _log('copy_gif_to_clipboard exception:\n' + traceback.format_exc())
        # Final fallback: copy path as text
        return copy_path_to_clipboard(gif_path)


def copy_file_to_clipboard_cfhdrop(path: str) -> bool:
    """Place a file path on the clipboard using CF_HDROP (Unicode DROPFILES)."""
    if sys.platform != 'win32':
        return False
    try:
        CF_HDROP = 15
        # DROPFILES header: DWORD pFiles; POINT pt (2 LONGs); BOOL fNC; BOOL fWide
        pFiles = 20  # header size in bytes
        pt_x = 0
        pt_y = 0
        fNC = 0
        fWide = 1
        header = struct.pack('<IiiII', pFiles, pt_x, pt_y, fNC, fWide)
        # Unicode file list: null-terminated wide string, terminated by extra null
        files_utf16 = os.path.abspath(path).encode('utf-16le') + b'\x00\x00'
        data = header + files_utf16 + b'\x00\x00'
        ok = _set_clipboard_data_win(CF_HDROP, data)
        if not ok:
            _log('copy_file_to_clipboard_cfhdrop: SetClipboardData CF_HDROP failed')
        return ok
    except Exception:
        _log('copy_file_to_clipboard_cfhdrop exception:\n' + traceback.format_exc())
        return False


def copy_gif_to_clipboard_pywin32(gif_path: str) -> bool:
    """Use pywin32 to attempt to write GIF binary to clipboard, with fallbacks."""
    if sys.platform != 'win32':
        return False
    try:
        import win32clipboard
        import win32con
    except Exception:
        _log('pywin32 not available')
        return False

    try:
        with open(gif_path, 'rb') as f:
            gif_data = f.read()
    except Exception:
        _log('pywin32: failed to read gif')
        return False

    try:
        win32clipboard.OpenClipboard()
        win32clipboard.EmptyClipboard()
        # register GIF format
        try:
            fmt = win32clipboard.RegisterClipboardFormat('GIF')
        except Exception:
            fmt = None
        ok = False
        if fmt:
            try:
                win32clipboard.SetClipboardData(fmt, gif_data)
                ok = True
            except Exception:
                _log('pywin32: SetClipboardData GIF exception:\n' + traceback.format_exc())
                ok = False

        if ok:
            _log('pywin32: wrote GIF custom format')
            return True

        # fallback: put first frame as DIB and also put path as unicode text
        try:
            im = Image.open(gif_path)
            im.seek(0)
            bio = io.BytesIO()
            im.convert('RGB').save(bio, format='BMP')
            bmp = bio.getvalue()
            dib = bmp[14:]
            try:
                win32clipboard.SetClipboardData(win32con.CF_DIB, dib)
            except Exception:
                _log('pywin32: CF_DIB SetClipboardData exception:\n' + traceback.format_exc())
            try:
                win32clipboard.SetClipboardData(win32con.CF_UNICODETEXT, os.path.abspath(gif_path))
            except Exception:
                _log('pywin32: CF_UNICODETEXT SetClipboardData exception:\n' + traceback.format_exc())
            _log('pywin32: wrote CF_DIB and CF_UNICODETEXT')
            return True
        except Exception:
            _log('pywin32 fallback exception:\n' + traceback.format_exc())
            return False
    finally:
        try:
            win32clipboard.CloseClipboard()
        except Exception:
            pass
import os
import os
import sys
import io
import ctypes
from typing import Optional
from PIL import Image
import traceback
from datetime import datetime
    try:
        import tkinter as tk
        root = tk.Tk()
        root.withdraw()
        root.clipboard_clear()
        root.clipboard_append(os.path.abspath(path))
        root.update()
        root.destroy()
        return True
    except Exception:
        try:
            import pyperclip
            pyperclip.copy(os.path.abspath(path))
            return True
        except Exception:
            return False


def _set_clipboard_data_win(format_id: int, data: bytes) -> bool:
    kernel32 = ctypes.windll.kernel32
    user32 = ctypes.windll.user32
    GMEM_MOVEABLE = 0x0002
    GMEM_ZEROINIT = 0x0040
    flags = GMEM_MOVEABLE | GMEM_ZEROINIT

    size = len(data)
    hGlobal = kernel32.GlobalAlloc(flags, size)
    if not hGlobal:
        return False
    lp = kernel32.GlobalLock(hGlobal)
    if not lp:
        kernel32.GlobalFree(hGlobal)
        return False
    # copy bytes into locked memory
    ctypes.memmove(lp, data, size)
    kernel32.GlobalUnlock(hGlobal)

    # Try opening clipboard with retries in case it's locked
    for attempt in range(5):
        if user32.OpenClipboard(0):
            break
        import time
        time.sleep(0.05)
    else:
        kernel32.GlobalFree(hGlobal)
        return False

    try:
        user32.EmptyClipboard()
        if not user32.SetClipboardData(format_id, hGlobal):
            # SetClipboardData failed; free and return
            _log_win_error('SetClipboardData failed', kernel32)
            kernel32.GlobalFree(hGlobal)
            return False
        # On success, Windows owns the handle; do not free
        return True
    finally:
        user32.CloseClipboard()


def copy_gif_to_clipboard(gif_path: str) -> bool:
    """Try to copy the GIF binary to the Windows clipboard.

    Strategy (Windows only):
    1. Register and set a custom 'GIF' clipboard format with raw GIF bytes.
    2. Fallback: put the first frame as CF_DIB and also put the file path as CF_UNICODETEXT.
    Returns True on (likely) success, False otherwise.
    """
    if sys.platform != 'win32':
        return False

    # Read GIF bytes
    try:
        with open(gif_path, 'rb') as f:
            gif_data = f.read()
    except Exception:
        return False

    user32 = ctypes.windll.user32
        # Try custom GIF format
    try:
            fmt = user32.RegisterClipboardFormatA(b'GIF')
        if fmt:
            ok = _set_clipboard_data_win(fmt, gif_data)
            if ok:
                return True
    except Exception:
            _log('copy_gif_to_clipboard: RegisterClipboardFormatA exception:\n' + traceback.format_exc())
            pass

    # Fallback: put first frame as CF_DIB and file path as CF_UNICODETEXT
    try:
        im = Image.open(gif_path)
        im.seek(0)
        bio = io.BytesIO()
        im.convert('RGB').save(bio, format='BMP')
        bmp = bio.getvalue()
        # BMP file has 14-byte BITMAPFILEHEADER; CF_DIB expects BITMAPINFOHEADER + data
        dib = bmp[14:]

        CF_DIB = 8
        CF_UNICODETEXT = 13

        # Put DIB
        if not _set_clipboard_data_win(CF_DIB, dib):
            # If DIB fails, still try to put the path text
            copy_path_to_clipboard(gif_path)
            return False

        # Put file path as Unicode text
        path_text = os.path.abspath(gif_path).encode('utf-16le') + b'\x00\x00'
        _set_clipboard_data_win(CF_UNICODETEXT, path_text)
        return True
    except Exception:
        # Final fallback: copy path as text
        return copy_path_to_clipboard(gif_path)


def copy_file_to_clipboard_cfhdrop(path: str) -> bool:
    """Place a file path on the clipboard using CF_HDROP (Unicode DROPFILES).

    Uses ctypes to build DROPFILES + wide-char filename list and calls
    _set_clipboard_data_win with CF_HDROP.
    """
    if sys.platform != 'win32':
        return False
    try:
        import struct
        CF_HDROP = 15
        # DROPFILES header: DWORD pFiles; POINT pt (2 LONGs); BOOL fNC; BOOL fWide
        pFiles = 20  # header size in bytes
        pt_x = 0
        pt_y = 0
        fNC = 0
        fWide = 1
        header = struct.pack('<IiiII', pFiles, pt_x, pt_y, fNC, fWide)
        # Unicode file list: null-terminated wide string, terminated by extra null
        files_utf16 = os.path.abspath(path).encode('utf-16le') + b'\x00\x00'
        data = header + files_utf16 + b'\x00\x00'
        return _set_clipboard_data_win(CF_HDROP, data)
    except Exception:
        return False


def copy_gif_to_clipboard_pywin32(gif_path: str) -> bool:
    """Use pywin32 to attempt to write GIF binary to clipboard, with fallbacks.

    Returns True if any clipboard write likely succeeded.
    """
    if sys.platform != 'win32':
        return False
    try:
        import win32clipboard
        import win32con
    except Exception:
        return False

    # read gif bytes
    try:
        with open(gif_path, 'rb') as f:
            gif_data = f.read()
    except Exception:
        return False

    try:
        win32clipboard.OpenClipboard()
        win32clipboard.EmptyClipboard()
        # register GIF format
        try:
            fmt = win32clipboard.RegisterClipboardFormat('GIF')
        except Exception:
            fmt = None
        ok = False
        if fmt:
            try:
                win32clipboard.SetClipboardData(fmt, gif_data)
                ok = True
            except Exception:
                ok = False

        if ok:
            return True

        # fallback: put first frame as DIB and also put path as unicode text
        im = Image.open(gif_path)
        im.seek(0)
        bio = io.BytesIO()
        im.convert('RGB').save(bio, format='BMP')
        bmp = bio.getvalue()
        dib = bmp[14:]
        try:
            win32clipboard.SetClipboardData(win32con.CF_DIB, dib)
        except Exception:
            # if DIB fails, don't abort; try to at least put the path text
            pass
        try:
            win32clipboard.SetClipboardData(win32con.CF_UNICODETEXT, os.path.abspath(gif_path))
        except Exception:
            pass
        return True
    finally:
        try:
            win32clipboard.CloseClipboard()
        except Exception:
            pass

    return False

