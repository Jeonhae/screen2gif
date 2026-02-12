"""Minimal clipboard helpers used by the app.

This module provides a compact, well-formed implementation so the
repository can be statically analyzed and the basic app features work.
On Windows, a richer `clipboard_win` module will be used when present.
"""

from __future__ import annotations

import os


def _copy_text(text: str) -> bool:
    """Copy plain text to the clipboard using tkinter or pyperclip."""
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
    """Copy an absolute filesystem path to the clipboard as text."""
    return _copy_text(os.path.abspath(path))


def copy_gif_to_clipboard(gif_path: str) -> bool:
    """Attempt to put a GIF onto the clipboard; fallback to path-as-text.

    On Windows, delegates to `clipboard_win` if available.
    """
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
            # If import or delegate fails, fall back to copying path text.
            pass
    return copy_path_to_clipboard(gif_path)


def copy_file_to_clipboard_cfhdrop(path: str) -> bool:
    """Place a file path on the clipboard using CF_HDROP on Windows.

    This implementation prefers a `clipboard_win` helper; otherwise it
    places the absolute path as text.
    """
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
