"""
Windows clipboard helpers (clean) for debugging.
This module mirrors the intended clipboard behavior and logs to logs/clipboard_debug.log.
"""

import os
import sys
import io
import ctypes
import struct
import traceback
from datetime import datetime
from PIL import Image

# set ctypes prototypes for kernel32/user32 functions to ensure correct pointer sizes
kernel32 = ctypes.windll.kernel32
user32 = ctypes.windll.user32
kernel32.GlobalAlloc.argtypes = (ctypes.c_uint, ctypes.c_size_t)
kernel32.GlobalAlloc.restype = ctypes.c_void_p
kernel32.GlobalLock.argtypes = (ctypes.c_void_p,)
kernel32.GlobalLock.restype = ctypes.c_void_p
kernel32.GlobalUnlock.argtypes = (ctypes.c_void_p,)
kernel32.GlobalUnlock.restype = ctypes.c_int
kernel32.GlobalFree.argtypes = (ctypes.c_void_p,)
kernel32.GlobalFree.restype = ctypes.c_int
kernel32.GetLastError.restype = ctypes.c_ulong
user32.OpenClipboard.argtypes = (ctypes.c_void_p,)
user32.OpenClipboard.restype = ctypes.c_int
user32.CloseClipboard.restype = ctypes.c_int
user32.EmptyClipboard.restype = ctypes.c_int
user32.SetClipboardData.argtypes = (ctypes.c_uint, ctypes.c_void_p)
user32.SetClipboardData.restype = ctypes.c_void_p


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
    ctypes.memmove(lp, data, size)
    kernel32.GlobalUnlock(hGlobal)

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
            try:
                err = kernel32.GetLastError()
            except Exception:
                err = None
            _log(f'SetClipboardData failed; err={err}')
            kernel32.GlobalFree(hGlobal)
            return False
        return True
    finally:
        user32.CloseClipboard()


def copy_gif_to_clipboard_pywin32(gif_path: str) -> bool:
    if sys.platform != 'win32':
        return False
    try:
        import win32clipboard, win32con
    except Exception:
        _log('pywin32 not installed')
        return False

    try:
        with open(gif_path, 'rb') as f:
            gif_data = f.read()
    except Exception:
        _log('failed to read gif file')
        return False

    try:
        win32clipboard.OpenClipboard()
        win32clipboard.EmptyClipboard()
        try:
            fmt = win32clipboard.RegisterClipboardFormat('GIF')
        except Exception:
            fmt = None
        if fmt:
            try:
                win32clipboard.SetClipboardData(fmt, gif_data)
                _log('pywin32: wrote GIF custom format')
                return True
            except Exception:
                _log('pywin32: SetClipboardData GIF failed:\n' + traceback.format_exc())

        # fallback DIB + path
        im = Image.open(gif_path)
        im.seek(0)
        bio = io.BytesIO()
        im.convert('RGB').save(bio, format='BMP')
        bmp = bio.getvalue()
        dib = bmp[14:]
        try:
            win32clipboard.SetClipboardData(win32con.CF_DIB, dib)
        except Exception:
            _log('pywin32: CF_DIB failed:\n' + traceback.format_exc())
        try:
            win32clipboard.SetClipboardData(win32con.CF_UNICODETEXT, os.path.abspath(gif_path))
        except Exception:
            _log('pywin32: CF_UNICODETEXT failed:\n' + traceback.format_exc())
        _log('pywin32: fallback wrote DIB+path')
        return True
    finally:
        try:
            win32clipboard.CloseClipboard()
        except Exception:
            pass


def copy_gif_to_clipboard_ctypes(gif_path: str) -> bool:
    if sys.platform != 'win32':
        return False
    try:
        with open(gif_path, 'rb') as f:
            gif_data = f.read()
    except Exception:
        _log('ctypes: failed to read gif')
        return False

    user32 = ctypes.windll.user32
    try:
        fmt = user32.RegisterClipboardFormatA(b'GIF')
    except Exception:
        fmt = None
    if fmt:
        ok = _set_clipboard_data_win(fmt, gif_data)
        _log(f'ctypes: Register GIF fmt={fmt} ok={ok}')
        if ok:
            return True

    # fallback to DIB+path
    try:
        im = Image.open(gif_path)
        im.seek(0)
        bio = io.BytesIO()
        im.convert('RGB').save(bio, format='BMP')
        bmp = bio.getvalue()
        dib = bmp[14:]
        ok = _set_clipboard_data_win(8, dib)
        if not ok:
            _log('ctypes: CF_DIB failed')
            return False
        path_text = os.path.abspath(gif_path).encode('utf-16le') + b'\x00\x00'
        ok2 = _set_clipboard_data_win(13, path_text)
        _log(f'ctypes: CF_DIB ok={ok} CF_UNICODETEXT ok={ok2}')
        return True
    except Exception:
        _log('ctypes fallback exception:\n' + traceback.format_exc())
        return False


def copy_file_to_clipboard_cfhdrop_ctypes(path: str) -> bool:
    if sys.platform != 'win32':
        return False
    try:
        pFiles = 20
        pt_x = 0
        pt_y = 0
        fNC = 0
        fWide = 1
        header = struct.pack('<IiiII', pFiles, pt_x, pt_y, fNC, fWide)
        files_utf16 = os.path.abspath(path).encode('utf-16le') + b'\x00\x00'
        data = header + files_utf16 + b'\x00\x00'
        ok = _set_clipboard_data_win(15, data)
        _log(f'cfhdrop ok={ok}')
        return ok
    except Exception:
        _log('cfhdrop exception:\n' + traceback.format_exc())
        return False
