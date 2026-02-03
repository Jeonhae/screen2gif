import sys
import traceback
import os
import time

# Crash Logger
log_dir = os.path.join(os.path.dirname(__file__), 'logs')
os.makedirs(log_dir, exist_ok=True)
crash_log = os.path.join(log_dir, 'crash_error.log')

def _log_exception(etype, value, tb):
    with open(crash_log, 'w', encoding='utf-8') as f:
        f.write(f"Timestamp: {time.time()}\n")
        f.write("".join(traceback.format_exception(etype, value, tb)))
    sys.__excepthook__(etype, value, tb)
sys.excepthook = _log_exception

try:
    from PyQt5 import QtWidgets, QtCore
    from overlay import OverlayWindow
    from toolbar import ToolBar
    from recorder import ScreenRecorder
    from converter import convert_mp4_to_gif
    from clipboard_clean import copy_path_to_clipboard
    from utils import ensure_dirs, timestamped_filename
except Exception:
    raise


def main():
    ensure_dirs()
    
    # Enable High DPI scaling
    if hasattr(QtCore.Qt, 'AA_EnableHighDpiScaling'):
        QtWidgets.QApplication.setAttribute(QtCore.Qt.AA_EnableHighDpiScaling, True)

    app = QtWidgets.QApplication(sys.argv)
    # Keep the application running even when all windows are hidden.
    # This prevents the app from exiting when overlay/toolbar are hidden
    # during capture (they are hidden to avoid appearing in the recording).
    app.setQuitOnLastWindowClosed(False)

    overlay = OverlayWindow()
    toolbar = ToolBar()

    # Ensure overlay is topmost so it sits above other apps, and toolbar will be raised above it
    try:
        overlay.setWindowFlag(QtCore.Qt.WindowStaysOnTopHint, True)
    except Exception:
        pass

    recorder = ScreenRecorder()

    # Ensure recorder thread is stopped when the application is quitting
    def _on_about_to_quit():
        try:
            if getattr(recorder, '_thread', None) and recorder._thread.is_alive():
                recorder._stop_event.set()
                recorder._thread.join(timeout=1)
        except Exception:
            pass
        try:
            _visibility_monitor.stop()
        except Exception:
            pass

    try:
        app.aboutToQuit.connect(_on_about_to_quit)
    except Exception:
        pass
    # Default selection will be set after showing overlay so mapping functions work

    def on_start(rect):
        x, y, w, h = rect
        output_mp4 = timestamped_filename('video', 'mp4')
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
                time.sleep(0.12)
        except Exception:
            pass

        # enter recording visual state on overlay (start blinking after exclusion applied)
        try:
            overlay.start_recording()
        except Exception:
            pass

        # Try to start recorder first. If recorder fails to initialize, do not hide UI.
        try:
            recorder.start((x, y, w, h), fps=10, out_path=output_mp4)
            # give the recorder a brief moment to start and validate it is running
            time.sleep(0.12)
            if not (getattr(recorder, '_thread', None) and recorder._thread.is_alive()):
                # recorder failed to start - surface error and return UI to main
                try:
                    QtWidgets.QMessageBox.warning(None, 'Error', 'Failed to start recorder')
                except Exception:
                    pass
                _return_to_main()
                return
        except Exception:
            try:
                QtWidgets.QMessageBox.warning(None, 'Error', 'Failed to start recorder')
            except Exception:
                pass
            _return_to_main()
            return

        # Start monitoring toolbar visibility so we can detect unexpected closes during capture
        try:
            _visibility_monitor.start()
        except Exception:
            pass

    def on_stop():
        mp4_path = recorder.stop()
        try:
            _visibility_monitor.stop()
        except Exception:
            pass
        # exit recording visual state and hide overlay
        try:
            overlay.stop_recording()
        except Exception:
            pass
        try:
            overlay.hide()
            toolbar.hide()
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
            _return_to_main()
            return

        gif_path = timestamped_filename('gif', 'gif')
        ok = convert_mp4_to_gif(mp4_path, gif_path, fps=10)
        if ok:
            copy_path_to_clipboard(gif_path)
            QtWidgets.QMessageBox.information(None, '完成', f'GIF已生成并复制至剪切板。\n路径:{gif_path}\n按Ctrl+V粘贴至目标位置。')
        else:
            QtWidgets.QMessageBox.warning(None, 'Error', 'Failed to convert to GIF')
        
        _return_to_main()

    # Initial launcher window
    class InitialWindow(QtWidgets.QWidget):
        record_requested = QtCore.pyqtSignal()

        def __init__(self):
            super().__init__()
            self.setWindowTitle('Screen2GIF')
            # Use a normal window so it reliably appears (not a tool window)
            self.setWindowFlags(QtCore.Qt.Window | QtCore.Qt.WindowStaysOnTopHint)
            layout = QtWidgets.QVBoxLayout()
            self.label = QtWidgets.QLabel('点击下方按钮进入录制模式')
            self.label.setAlignment(QtCore.Qt.AlignCenter)
            self.record_btn = QtWidgets.QPushButton('录制')
            layout.addWidget(self.label)
            layout.addWidget(self.record_btn)
            self.setLayout(layout)
            self.record_btn.clicked.connect(self.record_requested.emit)

        def closeEvent(self, event):
            try:
                _shutdown_app()
            finally:
                super().closeEvent(event)

    initial = InitialWindow()

    def _return_to_main():
        # Stop any active recording/countdown
        # If application is in shutdown, don't reopen the initial window
        try:
            inst = QtWidgets.QApplication.instance()
            if inst and inst.closingDown():
                return
        except Exception:
            pass
        if getattr(recorder, '_thread', None) and recorder._thread.is_alive():
            recorder.stop()
        try:
            _visibility_monitor.stop()
        except Exception:
            pass
        try:
            _countdown_timer.stop()
        except: pass

        # Reset UI
        try:
            overlay.stop_recording()
            overlay.hide()
            toolbar.hide()
            toolbar.start_btn.setEnabled(True)
            toolbar.start_btn.setText('Start')
        except Exception:
            pass
        
        initial.showNormal()
        initial.raise_()
        initial.activateWindow()

    # Shared timer for countdown
    _countdown_timer = QtCore.QTimer()
    _cnt_val = [5]

    # Monitor toolbar visibility during recording. If toolbar disappears unexpectedly
    # while recorder thread is alive, quit the application so the terminal shows exit.
    _visibility_monitor = QtCore.QTimer()
    _visibility_monitor.setInterval(300)

    def _monitor_check():
        try:
            if getattr(recorder, '_thread', None) and recorder._thread.is_alive():
                # If toolbar is not visible and we didn't just hide it intentionally for capture,
                # assume an abnormal UI exit and quit the app so terminal exits.
                if not toolbar.isVisible():
                    try:
                        dbgdir = os.path.join(os.path.dirname(__file__), 'logs')
                        os.makedirs(dbgdir, exist_ok=True)
                        with open(os.path.join(dbgdir, 'capture_process_debug.txt'), 'a', encoding='utf-8') as df:
                            df.write(f"visibility_monitor triggered: toolbar_visible={toolbar.isVisible()} time={time.time()}\n")
                    except Exception:
                        pass
                    try:
                        QtWidgets.QApplication.quit()
                    except Exception:
                        try:
                            sys.exit(1)
                        except Exception:
                            pass
        except Exception:
            pass

    try:
        try:
            _visibility_monitor.timeout.disconnect()
        except Exception:
            pass
        _visibility_monitor.timeout.connect(_monitor_check)
    except Exception:
        pass

    _shutdown_initiated = [False]

    def _shutdown_app():
        if _shutdown_initiated[0]:
            return
        _shutdown_initiated[0] = True
        try:
            _countdown_timer.stop()
        except Exception:
            pass
        try:
            _visibility_monitor.stop()
        except Exception:
            pass
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
            overlay.hide()
            toolbar.hide()
            initial.hide()
        except Exception:
            pass
        try:
            QtWidgets.QApplication.quit()
        except Exception:
            try:
                sys.exit(0)
            except Exception:
                pass

    def _handle_start_clicked():
        # If overlay is hidden for some reason, just show it
        if not overlay.isVisible():
            overlay.showFullScreen()
            return
        
        # Start countdown
        toolbar.start_btn.setEnabled(False)
        _cnt_val[0] = 5
        toolbar.start_btn.setText(str(_cnt_val[0]))

        def _tick():
            _cnt_val[0] -= 1
            if _cnt_val[0] > 0:
                toolbar.start_btn.setText(str(_cnt_val[0]))
            else:
                _countdown_timer.stop()
                try:
                    _countdown_timer.timeout.disconnect()
                except: pass
                toolbar.start_btn.setText("Recording...")
                
                # Start recording
                # Use an inset capture region so the overlay's red border isn't recorded
                sel = overlay.get_capture_region(padding=3)
                on_start(sel)

        try:
            _countdown_timer.timeout.disconnect()
        except: pass
        _countdown_timer.timeout.connect(_tick)
        _countdown_timer.start(1000)

    def _handle_toolbar_close():
        _shutdown_app()

    toolbar.start_requested.connect(_handle_start_clicked)
    toolbar.stop_requested.connect(on_stop)
    toolbar.close_requested.connect(_handle_toolbar_close)

    def _enter_record_mode():
        # Reset any previous state
        try:
            _countdown_timer.stop()
        except: pass
        toolbar.start_btn.setEnabled(True)
        toolbar.start_btn.setText('Start')

        # Show overlay and toolbar when user clicks "录制"
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
        # hide the initial launcher window
        try:
            initial.hide()
        except Exception:
            pass

        # Set default selection after overlay is shown
        try:
            geom = QtWidgets.QApplication.primaryScreen().geometry()
            w, h = 100, 100
            cx = geom.x() + max(0, (geom.width() - w) // 2)
            cy = geom.y() + max(0, (geom.height() - h) // 2)
            top_left = overlay.mapFromGlobal(QtCore.QPoint(cx, cy))
            overlay.selection_rect = QtCore.QRect(top_left.x(), top_left.y(), w, h)
            try:
                overlay.update_control_handles()
            except Exception:
                pass
        except Exception:
            pass

    initial.record_requested.connect(_enter_record_mode)
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
    # Show the initial launcher window (do not enter recording until user requests)
    try:
        # center and show the initial window as a normal window
        initial.resize(300, 120)
        screen_geom = QtWidgets.QApplication.primaryScreen().availableGeometry()
        x = screen_geom.x() + (screen_geom.width() - initial.width()) // 2
        y = screen_geom.y() + (screen_geom.height() - initial.height()) // 2
        initial.setGeometry(x, y, initial.width(), initial.height())
        initial.showNormal()
        initial.raise_()
        initial.activateWindow()
    except Exception:
        initial.show()
    # Debug code removed

    try:
        rc = app.exec_()
        try:
            with open(trace_path, 'a', encoding='utf-8') as tf:
                tf.write(f'app.exec_ returned {rc}\n')
        except Exception:
            pass
        sys.exit(rc)
    except Exception as e:
        try:
            with open(trace_path, 'a', encoding='utf-8') as tf:
                tf.write(f'app.exec_ raised: {e}\n')
        except Exception:
            pass
        raise


if __name__ == '__main__':
    main()
