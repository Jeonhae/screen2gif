"""Package wrapper: clipboard module copied into package so tests can import
`screen2gif.clipboard`.
"""

from __future__ import annotations

import os


def _copy_text(text: str) -> bool:
    try:
        import tkinter as tk

        root = tk.Tk()
        root.withdraw()
        root.clipboard_clear()
        root.clipboard_append(text)
        root.update()
        root.destroy()
        return True
    except Exception:
        try:
            import pyperclip

            pyperclip.copy(text)
            return True
        except Exception:
            return False


def copy_path_to_clipboard(path: str) -> bool:
    return _copy_text(os.path.abspath(path))


def copy_gif_to_clipboard(gif_path: str) -> bool:
    if os.name == "nt":
        try:
            from . import clipboard_win as _cw  # type: ignore

            if hasattr(_cw, "copy_gif_to_clipboard_ctypes"):
                try:
                    return _cw.copy_gif_to_clipboard_ctypes(gif_path)
                except Exception:
                    pass
            if hasattr(_cw, "copy_gif_to_clipboard_pywin32"):
                try:
                    return _cw.copy_gif_to_clipboard_pywin32(gif_path)
                except Exception:
                    pass
        except Exception:
            pass
    return copy_path_to_clipboard(gif_path)


def copy_gif_to_clipboard_pywin32(gif_path: str) -> bool:
    if os.name != "nt":
        return False
    try:
        from . import clipboard_win as _cw  # type: ignore

        if hasattr(_cw, "copy_gif_to_clipboard_pywin32"):
            try:
                return _cw.copy_gif_to_clipboard_pywin32(gif_path)
            except Exception:
                pass
    except Exception:
        pass
    # fallback to generic behavior
    return copy_gif_to_clipboard(gif_path)


def copy_gif_to_clipboard_ctypes(gif_path: str) -> bool:
    if os.name != "nt":
        return False
    try:
        from . import clipboard_win as _cw  # type: ignore

        if hasattr(_cw, "copy_gif_to_clipboard_ctypes"):
            try:
                return _cw.copy_gif_to_clipboard_ctypes(gif_path)
            except Exception:
                pass
    except Exception:
        pass
    return copy_gif_to_clipboard(gif_path)


def copy_file_to_clipboard_cfhdrop_ctypes(path: str) -> bool:
    if os.name != "nt":
        return False
    try:
        from . import clipboard_win as _cw  # type: ignore

        if hasattr(_cw, "copy_file_to_clipboard_cfhdrop_ctypes"):
            try:
                return _cw.copy_file_to_clipboard_cfhdrop_ctypes(path)
            except Exception:
                pass
    except Exception:
        pass
    return copy_file_to_clipboard_cfhdrop(path)


def copy_file_to_clipboard_cfhdrop(path: str) -> bool:
    if os.name == "nt":
        try:
            from . import clipboard_win as _cw  # type: ignore

            if hasattr(_cw, "copy_file_to_clipboard_cfhdrop_ctypes"):
                try:
                    return _cw.copy_file_to_clipboard_cfhdrop_ctypes(path)
                except Exception:
                    pass
        except Exception:
            pass
    return copy_path_to_clipboard(path)
