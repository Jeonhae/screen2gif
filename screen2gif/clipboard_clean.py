"""Clean cross-platform clipboard wrapper for screen2gif.

Prefers CF_HDROP on Windows via clipboard_win; falls back to copying file path text.
"""
import os
import sys
from datetime import datetime


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


if sys.platform == "win32":
    try:
        # Try absolute import first (works when scripts are run directly)
        from clipboard_win import (
            copy_file_to_clipboard_cfhdrop_ctypes,
            copy_gif_to_clipboard_ctypes,
            copy_gif_to_clipboard_pywin32,
        )
    except Exception:
        try:
            # Fallback to package-relative import
            from .clipboard_win import (
                copy_file_to_clipboard_cfhdrop_ctypes,
                copy_gif_to_clipboard_ctypes,
                copy_gif_to_clipboard_pywin32,
            )
        except Exception:
            def copy_file_to_clipboard_cfhdrop_ctypes(path: str) -> bool:  # type: ignore
                return False

            def copy_gif_to_clipboard_ctypes(path: str) -> bool:  # type: ignore
                return False

            def copy_gif_to_clipboard_pywin32(path: str) -> bool:  # type: ignore
                return False


    def copy_gif_to_clipboard(path: str) -> bool:
        try:
            if copy_file_to_clipboard_cfhdrop_ctypes(path):
                return True
        except Exception:
            pass
        try:
            if copy_gif_to_clipboard_ctypes(path):
                return True
        except Exception:
            pass
        try:
            return copy_gif_to_clipboard_pywin32(path)
        except Exception:
            return False


    def copy_path_to_clipboard(path: str) -> bool:
        _log(f'copy_path_to_clipboard called: {path}')
        results = []
        try:
            ok = copy_file_to_clipboard_cfhdrop_ctypes(path)
            results.append(('cfhdrop_ctypes', ok))
            if ok:
                _log('copy_path_to_clipboard: cfhdrop_ctypes succeeded')
                return True
        except Exception as e:
            results.append(('cfhdrop_ctypes', False))
            _log('copy_path_to_clipboard: cfhdrop_ctypes exception: ' + str(e))
        try:
            ok = copy_gif_to_clipboard_ctypes(path)
            results.append(('gif_ctypes', ok))
            if ok:
                _log('copy_path_to_clipboard: gif_ctypes succeeded')
                return True
        except Exception as e:
            results.append(('gif_ctypes', False))
            _log('copy_path_to_clipboard: gif_ctypes exception: ' + str(e))
        try:
            ok = copy_gif_to_clipboard_pywin32(path)
            results.append(('pywin32', ok))
            if ok:
                _log('copy_path_to_clipboard: pywin32 succeeded')
                return True
        except Exception as e:
            results.append(('pywin32', False))
            _log('copy_path_to_clipboard: pywin32 exception: ' + str(e))
        _log('copy_path_to_clipboard results: ' + str(results))
        return False

else:
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
