from PyQt5 import QtWidgets, QtCore
import sys

from overlay import OverlayWindow
from toolbar import ToolBar
from recorder import ScreenRecorder
from converter import convert_mp4_to_gif
from clipboard_clean import copy_path_to_clipboard
from utils import ensure_dirs, timestamped_filename


def main():
    ensure_dirs()
    app = QtWidgets.QApplication(sys.argv)

    overlay = OverlayWindow()
    toolbar = ToolBar()

    # Ensure overlay is topmost so it sits above other apps, and toolbar will be raised above it
    try:
        overlay.setWindowFlag(QtCore.Qt.WindowStaysOnTopHint, True)
    except Exception:
        pass

    recorder = ScreenRecorder()

    # Default selection will be set after showing overlay so mapping functions work

    def on_start(rect):
        x, y, w, h = rect
        output_mp4 = timestamped_filename('video', 'mp4')
        # enter recording visual state on overlay
        try:
            overlay.start_recording()
        except Exception:
            pass
        # Try to exclude overlay and toolbar windows from being captured (Windows only)
        try:
            if sys.platform == 'win32':
                import ctypes, time
                dwm = ctypes.windll.dwmapi
                user32 = ctypes.windll.user32
                DWMWA_EXCLUDED_FROM_CAPTURE = 17
                val = ctypes.c_int(1)
                try:
                    ov_hwnd = int(overlay.winId())
                    tb_hwnd = int(toolbar.winId())
                    dwm.DwmSetWindowAttribute(ov_hwnd, DWMWA_EXCLUDED_FROM_CAPTURE, ctypes.byref(val), ctypes.sizeof(val))
                    dwm.DwmSetWindowAttribute(tb_hwnd, DWMWA_EXCLUDED_FROM_CAPTURE, ctypes.byref(val), ctypes.sizeof(val))
                except Exception:
                    pass
                # small delay to allow OS to apply attribute
                time.sleep(0.05)
        except Exception:
            pass
        recorder.start((x, y, w, h), fps=10, out_path=output_mp4)

    def on_stop():
        mp4_path = recorder.stop()
        # exit recording visual state and hide overlay
        try:
            overlay.stop_recording()
        except Exception:
            pass
        try:
            overlay.hide()
        except Exception:
            pass
        # Clear DWM exclusion flags so windows behave normally again
        try:
            if sys.platform == 'win32':
                import ctypes
                dwm = ctypes.windll.dwmapi
                DWMWA_EXCLUDED_FROM_CAPTURE = 17
                val0 = ctypes.c_int(0)
                try:
                    ov_hwnd = int(overlay.winId())
                    tb_hwnd = int(toolbar.winId())
                    dwm.DwmSetWindowAttribute(ov_hwnd, DWMWA_EXCLUDED_FROM_CAPTURE, ctypes.byref(val0), ctypes.sizeof(val0))
                    dwm.DwmSetWindowAttribute(tb_hwnd, DWMWA_EXCLUDED_FROM_CAPTURE, ctypes.byref(val0), ctypes.sizeof(val0))
                except Exception:
                    pass
        except Exception:
            pass
        if not mp4_path:
            QtWidgets.QMessageBox.warning(None, 'Error', 'No recording produced')
            return
        gif_path = timestamped_filename('gif', 'gif')
        ok = convert_mp4_to_gif(mp4_path, gif_path, fps=10)
        if ok:
            copy_path_to_clipboard(gif_path)
            QtWidgets.QMessageBox.information(None, 'Done', f'GIF saved to {gif_path} and path copied to clipboard')
        else:
            QtWidgets.QMessageBox.warning(None, 'Error', 'Failed to convert to GIF')

    def _handle_start_clicked():
        # If overlay is hidden, show it for selection; otherwise start recording with current selection
        if not overlay.isVisible():
            overlay.showFullScreen()
            return
        # Use an inset capture region so the overlay's red border isn't recorded
        sel = overlay.get_capture_region(padding=3)
        on_start(sel)

    toolbar.start_requested.connect(_handle_start_clicked)
    toolbar.stop_requested.connect(on_stop)
    def on_cancel():
        # User cancelled: stop any active recording, exit recording UI and clear selection
        try:
            if getattr(recorder, '_thread', None) and recorder._thread.is_alive():
                recorder.stop()
        except Exception:
            pass
        try:
            overlay.stop_recording()
        except Exception:
            pass
        try:
            overlay.selection_rect = None
            overlay.update_control_handles()
            overlay.update()
            overlay.hide()
        except Exception:
            pass

    toolbar.cancel_requested.connect(on_cancel)
    # Ensure cancel closes the app entirely
    def _on_cancel_and_quit():
        try:
            on_cancel()
        except Exception:
            pass
        try:
            toolbar.close()
        except Exception:
            pass
        try:
            overlay.close()
        except Exception:
            pass
        # Quit the QApplication
        try:
            app.quit()
        except Exception:
            try:
                import sys
                sys.exit(0)
            except Exception:
                pass

    # replace cancel connection so Cancel quits the program
    toolbar.cancel_requested.disconnect(on_cancel)
    toolbar.cancel_requested.connect(_on_cancel_and_quit)

    # Show overlay (topmost) then raise the toolbar above it so toolbar is highest
    try:
        overlay.showFullScreen()
        overlay.raise_()
    except Exception:
        overlay.showFullScreen()
    try:
        toolbar.setWindowFlag(QtCore.Qt.WindowStaysOnTopHint, True)
        toolbar.show()
        toolbar.raise_()
        toolbar.activateWindow()
    except Exception:
        pass
    # Keep toolbar above overlay during interactions: bring-to-front when overlay emits interaction
    try:
        def _bring_toolbar_top():
            try:
                toolbar.raise_()
                toolbar.activateWindow()
                if sys.platform == 'win32':
                    import ctypes
                    user32 = ctypes.windll.user32
                    SWP_NOSIZE = 0x0001
                    SWP_NOMOVE = 0x0002
                    SWP_SHOWWINDOW = 0x0040
                    HWND_TOPMOST = -1
                    tb_hwnd = int(toolbar.winId())
                    user32.SetWindowPos(tb_hwnd, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW)
            except Exception:
                pass

        overlay.interaction.connect(_bring_toolbar_top)
    except Exception:
        pass
    # On Windows, explicitly adjust Z-order using SetWindowPos to ensure toolbar is above overlay
    try:
        if sys.platform == 'win32':
            import ctypes
            user32 = ctypes.windll.user32
            SWP_NOSIZE = 0x0001
            SWP_NOMOVE = 0x0002
            SWP_SHOWWINDOW = 0x0040
            HWND_TOPMOST = -1
            # get native window ids
            try:
                ov_hwnd = int(overlay.winId())
                tb_hwnd = int(toolbar.winId())
                # make overlay topmost
                user32.SetWindowPos(ov_hwnd, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW)
                # then make toolbar topmost (this call should place toolbar above overlay)
                user32.SetWindowPos(tb_hwnd, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW)
                # Best-effort: request the OS to exclude the toolbar window from screen capture
                try:
                    dwm = ctypes.windll.dwmapi
                    DWMWA_EXCLUDED_FROM_CAPTURE = 17
                    val = ctypes.c_int(1)
                    # DwmSetWindowAttribute(hwnd, attr, pvAttribute, cbAttribute)
                    dwm.DwmSetWindowAttribute(tb_hwnd, DWMWA_EXCLUDED_FROM_CAPTURE, ctypes.byref(val), ctypes.sizeof(val))
                except Exception:
                    pass
                try:
                    # Also try SetWindowDisplayAffinity as a fallback
                    WDA_NONE = 0
                    WDA_EXCLUDEFROMCAPTURE = 0x11
                    user32.SetWindowDisplayAffinity(tb_hwnd, WDA_EXCLUDEFROMCAPTURE)
                except Exception:
                    pass
            except Exception:
                pass
    except Exception:
        pass
    # Set default selection: centered 100x100 rectangle (after overlay is shown)
    try:
        geom = QtWidgets.QApplication.primaryScreen().geometry()
        w, h = 100, 100
        cx = geom.x() + max(0, (geom.width() - w) // 2)
        cy = geom.y() + max(0, (geom.height() - h) // 2)
        # map global to overlay-local
        top_left = overlay.mapFromGlobal(QtCore.QPoint(cx, cy))
        overlay.selection_rect = QtCore.QRect(top_left.x(), top_left.y(), w, h)
        try:
            overlay.update_control_handles()
        except Exception:
            pass
    except Exception:
        pass
    toolbar.show()

    sys.exit(app.exec_())


if __name__ == '__main__':
    main()
