import sys
import traceback
import os
import time
import logging
import shutil

# Default target size for produced GIFs (bytes). Change to adjust shrink threshold.
DEFAULT_GIF_TARGET_BYTES = 9 * 1024 * 1024

# Crash Logger
log_dir = os.path.join(os.path.dirname(__file__), "logs")
os.makedirs(log_dir, exist_ok=True)
crash_log = os.path.join(log_dir, "crash_error.log")

# Application log file
app_log = os.path.join(log_dir, "app.log")
logging.basicConfig(
    filename=app_log,
    level=logging.DEBUG,
    format="%(asctime)s %(levelname)s:%(name)s:%(message)s",
)

# Trace path used for lightweight trace records
trace_path = os.path.join(log_dir, "trace.log")


def _log_exception(etype, value, tb):
    with open(crash_log, "w", encoding="utf-8") as f:
        f.write(f"Timestamp: {time.time()}\n")
        f.write("".join(traceback.format_exception(etype, value, tb)))
    sys.__excepthook__(etype, value, tb)


sys.excepthook = _log_exception

try:
    from PyQt5 import QtWidgets
    from PyQt5 import QtCore
    from overlay import OverlayWindow
    from toolbar import ToolBar
    from recorder import ScreenRecorder
    from converter import convert_mp4_to_gif
    from clipboard_clean import copy_path_to_clipboard
    from utils import (
        ensure_dirs,
        timestamped_filename,
        clear_video_folder,
        clear_gif_folder,
        shrink_gif_to_target,
    )
except Exception:
    raise


def show_topmost_message(
    parent,
    title,
    text,
    icon=QtWidgets.QMessageBox.Information,
    buttons=QtWidgets.QMessageBox.Ok,
    modal=True,
    force_exec=True,
):
    """Create and show a top-most message box and return exec_() result.

    This helper ensures the dialog is raised/activated and on Windows
    attempts to set HWND_TOPMOST via SetWindowPos so it reliably
    appears above overlay/toolbar windows.
    """
    try:
        msg = QtWidgets.QMessageBox(parent)
        # Disable the window close (X) button so users must use the message buttons
        try:
            msg.setWindowFlag(QtCore.Qt.WindowCloseButtonHint, False)
        except Exception:
            pass
        msg.setIcon(icon)
        msg.setWindowTitle(title)
        msg.setText(text)
        msg.setStandardButtons(buttons)
        if modal:
            msg.setWindowModality(QtCore.Qt.ApplicationModal)
        try:
            msg.setWindowFlags(
                msg.windowFlags() | QtCore.Qt.Window | QtCore.Qt.WindowStaysOnTopHint
            )
        except Exception:
            logging.exception("setWindowFlags failed in show_topmost_message")
        try:
            msg.show()
            msg.raise_()
            msg.activateWindow()
        except Exception:
            logging.exception("show/raise/activate failed in show_topmost_message")
        if sys.platform == "win32":
            try:
                import ctypes

                SWP_NOSIZE = 0x0001
                SWP_NOMOVE = 0x0002
                SWP_SHOWWINDOW = 0x0040
                HWND_TOPMOST = -1
                try:
                    hwnd = int(msg.winId())
                    ctypes.windll.user32.SetWindowPos(
                        hwnd,
                        HWND_TOPMOST,
                        0,
                        0,
                        0,
                        0,
                        SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW,
                    )
                except Exception:
                    logging.exception("SetWindowPos failed in show_topmost_message")
            except Exception:
                logging.exception("Platform-specific topmost logic failed")
        if force_exec:
            try:
                ret = msg.exec_()
            except Exception:
                try:
                    ret = QtWidgets.QMessageBox.Ok
                except Exception:
                    ret = None

            # After the dialog is closed, try to restore focus to the toolbar
            try:
                for w in QtWidgets.QApplication.topLevelWidgets():
                    if hasattr(w, "start_btn"):
                        try:
                            w.raise_()
                            w.activateWindow()
                            w.start_btn.setFocus()
                        except Exception:
                            pass
                        break
            except Exception:
                pass

            return ret
    except Exception:
        logging.exception("show_topmost_message failed")
        return None
    return None


def show_nonoverlapping_message(
    toolbar_widget,
    parent,
    title,
    text,
    icon=QtWidgets.QMessageBox.Information,
    buttons=QtWidgets.QMessageBox.Ok,
):
    """Show a topmost message box positioned to avoid overlapping the toolbar.

    The dialog will be placed below the `toolbar_widget` centered by default.
    If there isn't enough space below, it will be placed above, then to the
    right or left as a fallback, finally centered on the screen. Returns
    the result of exec_().
    """
    try:
        msg = QtWidgets.QMessageBox(parent)
        msg.setIcon(icon)
        msg.setWindowTitle(title)
        msg.setText(text)
        msg.setStandardButtons(buttons)
        msg.setWindowFlags(
            msg.windowFlags() | QtCore.Qt.Window | QtCore.Qt.WindowStaysOnTopHint
        )

        msg.adjustSize()
        size = msg.sizeHint()
        dlg_w = size.width()
        dlg_h = size.height()

        try:
            tb_rect = toolbar_widget.frameGeometry()
            try:
                screen = QtWidgets.QApplication.screenAt(tb_rect.center())
            except Exception:
                screen = QtWidgets.QApplication.primaryScreen()
            if screen:
                avail = screen.availableGeometry()
            else:
                avail = QtWidgets.QApplication.primaryScreen().availableGeometry()

            margin = 8
            x = tb_rect.x() + (tb_rect.width() - dlg_w) // 2
            y = tb_rect.y() + tb_rect.height() + margin
            if y + dlg_h <= avail.y() + avail.height() - margin:
                pass
            else:
                y2 = tb_rect.y() - dlg_h - margin
                if y2 >= avail.y() + margin:
                    y = y2
                else:
                    x2 = tb_rect.x() + tb_rect.width() + margin
                    y2 = tb_rect.y() + (tb_rect.height() - dlg_h) // 2
                    if x2 + dlg_w <= avail.x() + avail.width() - margin:
                        x = x2
                        y = max(
                            avail.y() + margin,
                            min(y2, avail.y() + avail.height() - dlg_h - margin),
                        )
                    else:
                        x2 = tb_rect.x() - dlg_w - margin
                        if x2 >= avail.x() + margin:
                            x = x2
                            y = max(
                                avail.y() + margin,
                                min(y2, avail.y() + avail.height() - dlg_h - margin),
                            )
                        else:
                            x = avail.x() + (avail.width() - dlg_w) // 2
                            y = avail.y() + (avail.height() - dlg_h) // 2
            try:
                msg.move(int(x), int(y))
            except Exception:
                logging.exception("Failed to position non-overlapping message")
        except Exception:
            try:
                screen = QtWidgets.QApplication.primaryScreen()
                avail = screen.availableGeometry()
                x = avail.x() + (avail.width() - dlg_w) // 2
                y = avail.y() + (avail.height() - dlg_h) // 2
                msg.move(int(x), int(y))
            except Exception:
                logging.exception(
                    "Fallback centering failed for non-overlapping message"
                )

        try:
            return msg.exec_()
        except Exception:
            return None
    except Exception:
        logging.exception("show_nonoverlapping_message failed")
        return None


def init_ui():
    """Create and configure UI objects used by the application.

    Returns (overlay, toolbar, recorder, countdown_timer, visibility_monitor).
    """
    overlay = OverlayWindow()
    toolbar = ToolBar()

    # Ensure overlay is topmost so it sits above other apps where appropriate.
    try:
        overlay.setWindowFlag(QtCore.Qt.WindowStaysOnTopHint, True)
    except Exception:
        logging.exception("Failed to set overlay topmost flag in init_ui")

    recorder = ScreenRecorder()

    # Shared timer for countdown
    countdown_timer = QtCore.QTimer()

    # Monitor toolbar visibility during recording.
    visibility_monitor = QtCore.QTimer()
    visibility_monitor.setInterval(300)

    return overlay, toolbar, recorder, countdown_timer, visibility_monitor


def monitor_check(ctx):
    """Visibility monitor callback extracted to module-level for clarity.

    Expects `ctx` to have `recorder`, `toolbar`, and optionally `logs` paths.
    """
    try:
        recorder = ctx.recorder
        toolbar = ctx.toolbar
        if getattr(recorder, "_thread", None) and recorder._thread.is_alive():
            if not toolbar.isVisible():
                try:
                    dbgdir = os.path.join(os.path.dirname(__file__), "logs")
                    os.makedirs(dbgdir, exist_ok=True)
                    with open(
                        os.path.join(dbgdir, "capture_process_debug.txt"),
                        "a",
                        encoding="utf-8",
                    ) as df:
                        ts = time.time()
                        df.write(
                            "visibility_monitor triggered: toolbar_visible="
                            + str(toolbar.isVisible())
                            + " time="
                            + str(ts)
                            + "\n"
                        )
                except Exception:
                    logging.exception("Failed writing visibility monitor debug")
                try:
                    QtWidgets.QApplication.quit()
                except Exception:
                    try:
                        sys.exit(1)
                    except Exception:
                        logging.exception("Failed to quit application in monitor_check")
    except Exception:
        logging.exception("monitor_check encountered an unexpected error")


def _process_ui_events_wait(ms: int = 120):
    """Process Qt events for up to `ms` milliseconds to allow UI state to settle.

    This replaces small blocking `time.sleep()` calls so the GUI can remain
    responsive while waiting for OS/window changes to take effect.
    """
    try:
        end = time.perf_counter() + (ms / 1000.0)
        app = QtWidgets.QApplication.instance()
        while time.perf_counter() < end:
            if app:
                try:
                    app.processEvents()
                except Exception:
                    pass
            time.sleep(0.01)
    except Exception:
        logging.exception("_process_ui_events_wait failed")


def start_recording_flow(ctx, rect):
    """Module-level flow to start recording given a context and selection rect.

    `ctx` is expected to provide: `overlay`, `toolbar`, `recorder`,
    `visibility_monitor`, and `return_to_main` (callable).
    """
    overlay = ctx.overlay
    toolbar = ctx.toolbar
    recorder = ctx.recorder
    visibility_monitor = ctx.visibility_monitor

    x, y, w, h = rect
    output_mp4 = timestamped_filename("video", "mp4")

    # Ensure video output folder is clean before writing a new recording.
    try:
        clear_video_folder()
    except Exception:
        logging.exception("clear_video_folder failed in start_recording_flow")

    # Try to exclude overlay and toolbar windows from being captured
    try:
        if sys.platform == "win32":
            try:
                from platform_win import get_hwnd, set_exclude_from_capture

                ov_hwnd = get_hwnd(overlay)
                tb_hwnd = get_hwnd(toolbar)
                if ov_hwnd:
                    set_exclude_from_capture(ov_hwnd, True)
                if tb_hwnd:
                    set_exclude_from_capture(tb_hwnd, True)
            except Exception:
                logging.exception("Windows capture exclusion failed in start_flow")
            try:
                _process_ui_events_wait(120)
            except Exception:
                pass
    except Exception:
        logging.exception("Unexpected error in start_recording_flow platform logic")

    try:
        overlay.start_recording()
    except Exception:
        logging.exception("overlay.start_recording failed in start_recording_flow")

    try:
        recorder.start((x, y, w, h), fps=10, out_path=output_mp4)
        _process_ui_events_wait(120)
        if not (getattr(recorder, "_thread", None) and recorder._thread.is_alive()):
            try:
                show_topmost_message(
                    None,
                    "Error",
                    "Failed to start recorder",
                    icon=QtWidgets.QMessageBox.Warning,
                )
            except Exception:
                logging.exception("show_topmost_message failed after recorder start")
            try:
                ctx.return_to_main()
            except Exception:
                logging.exception("return_to_main failed after recorder start")
            return
    except Exception:
        try:
            show_topmost_message(
                None,
                "Error",
                "Failed to start recorder",
                icon=QtWidgets.QMessageBox.Warning,
            )
        except Exception:
            logging.exception("show_topmost_message failed on recorder exception")
        try:
            ctx.return_to_main()
        except Exception:
            logging.exception("return_to_main failed on recorder exception")
        return

    try:
        visibility_monitor.start()
    except Exception:
        logging.exception("visibility_monitor.start failed in start_recording_flow")


def stop_recording_flow(ctx):
    """Module-level flow to stop recording and handle conversion/clipboard."""
    overlay = ctx.overlay
    toolbar = ctx.toolbar
    recorder = ctx.recorder
    visibility_monitor = ctx.visibility_monitor

    mp4_path = recorder.stop()
    try:
        visibility_monitor.stop()
    except Exception:
        logging.exception("visibility_monitor.stop failed in stop_recording_flow")

    try:
        overlay.stop_recording()
    except Exception:
        logging.exception("overlay.stop_recording failed in stop_recording_flow")
    try:
        overlay.hide()
        toolbar.hide()
    except Exception:
        logging.exception("Failed hiding UI in stop_recording_flow")

    try:
        if sys.platform == "win32":
            try:
                from platform_win import get_hwnd, set_exclude_from_capture

                ov_hwnd = get_hwnd(overlay)
                tb_hwnd = get_hwnd(toolbar)
                if ov_hwnd:
                    set_exclude_from_capture(ov_hwnd, False)
                if tb_hwnd:
                    set_exclude_from_capture(tb_hwnd, False)
            except Exception:
                logging.exception("Windows capture exclusion reset failed in stop_flow")
    except Exception:
        logging.exception("Unexpected error in stop_recording_flow platform logic")

    if not mp4_path:
        try:
            show_topmost_message(
                None,
                "Error",
                "No recording produced",
                icon=QtWidgets.QMessageBox.Warning,
            )
        except Exception:
            logging.exception("show_topmost_message failed in stop_recording_flow")
        try:
            ctx.return_to_main()
        except Exception:
            logging.exception("return_to_main failed in stop_recording_flow")
        return

    # clear previous GIFs before creating a new one
    try:
        clear_gif_folder()
    except Exception:
        logging.exception("Failed to clear gif folder before writing new GIF")

    gif_path = timestamped_filename("gif", "gif")
    ok = convert_mp4_to_gif(mp4_path, gif_path, fps=10)
    if ok:
        try:
            try:
                orig_size = os.path.getsize(gif_path)
            except Exception:
                orig_size = 0

            small_dir = os.path.join(os.path.dirname(__file__), "smallGif")
            if orig_size <= DEFAULT_GIF_TARGET_BYTES:
                try:
                    os.makedirs(small_dir, exist_ok=True)
                    dst = os.path.join(small_dir, os.path.basename(gif_path))
                    shutil.copy2(gif_path, dst)
                    gif_path = dst
                except Exception:
                    logging.exception("Failed copying small GIF to smallGif")
            else:
                try:
                    shr = shrink_gif_to_target(
                        gif_path, DEFAULT_GIF_TARGET_BYTES, small_dir
                    )
                    if shr:
                        gif_path = shr
                except Exception:
                    logging.exception("GIF shrinking failed in stop_recording_flow")
        except Exception:
            logging.exception("GIF shrinking failed in stop_recording_flow")
        copied_ok = False
        try:
            copied_ok = bool(copy_path_to_clipboard(gif_path))
        except Exception:
            logging.exception("copy_path_to_clipboard failed in stop_recording_flow")
        try:
            if copied_ok:
                show_topmost_message(
                    None,
                    "Success",
                    f"GIF generated and copied to clipboard.\nPath: {gif_path}\nPress Ctrl+V to paste.",
                    icon=QtWidgets.QMessageBox.Information,
                )
            else:
                show_topmost_message(
                    None,
                    "GIF generated",
                    f"GIF generated, but failed to copy to clipboard.\nPath: {gif_path}",
                    icon=QtWidgets.QMessageBox.Warning,
                )
        except Exception:
            logging.exception("show_topmost_message failed after convert")
    else:
        try:
            show_topmost_message(
                None,
                "Error",
                "Failed to convert to GIF",
                icon=QtWidgets.QMessageBox.Warning,
            )
        except Exception:
            logging.exception("show_topmost_message failed on convert error")

    try:
        ctx.return_to_main()
    except Exception:
        logging.exception("return_to_main failed at end of stop_recording_flow")


def main():
    ensure_dirs()

    # Enable High DPI scaling
    if hasattr(QtCore.Qt, "AA_EnableHighDpiScaling"):
        QtWidgets.QApplication.setAttribute(QtCore.Qt.AA_EnableHighDpiScaling, True)

    app = QtWidgets.QApplication(sys.argv)
    # Keep the application running even when all windows are hidden.
    # This prevents the app from exiting when overlay/toolbar are hidden
    # during capture (they are hidden to avoid appearing in the recording).
    app.setQuitOnLastWindowClosed(False)

    # Use module-level `show_topmost_message` helper

    # Use module-level `show_nonoverlapping_message` helper

    overlay, toolbar, recorder, _countdown_timer, _visibility_monitor = init_ui()

    # Ensure recorder thread is stopped when the application is quitting
    def _on_about_to_quit():
        try:
            if getattr(recorder, "_thread", None) and recorder._thread.is_alive():
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
        try:
            start_recording_flow(_ctx, rect)
        except Exception:
            logging.exception("start_recording_flow raised in on_start")

    def on_stop():
        try:
            stop_recording_flow(_ctx)
        except Exception:
            logging.exception("stop_recording_flow raised in on_stop")

    # Initial launcher window
    class InitialWindow(QtWidgets.QWidget):
        record_requested = QtCore.pyqtSignal()

        def __init__(self):
            super().__init__()
            self.setWindowTitle("Screen2GIF")
            # Use a normal window so it reliably appears (not a tool window)
            self.setWindowFlags(QtCore.Qt.Window | QtCore.Qt.WindowStaysOnTopHint)
            # Disable the maximize button for this initial launcher window
            try:
                self.setWindowFlag(QtCore.Qt.WindowMaximizeButtonHint, False)
            except Exception:
                pass
            layout = QtWidgets.QVBoxLayout()
            # author/credit label above the main instruction
            try:
                self.by_label = QtWidgets.QLabel("By译路同行")
                self.by_label.setAlignment(QtCore.Qt.AlignCenter)
                layout.addWidget(self.by_label)
            except Exception:
                pass
            self.label = QtWidgets.QLabel("点击下方按钮进入录制模式")
            self.label.setAlignment(QtCore.Qt.AlignCenter)
            self.record_btn = QtWidgets.QPushButton("录制")
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
        if getattr(recorder, "_thread", None) and recorder._thread.is_alive():
            recorder.stop()
        try:
            _visibility_monitor.stop()
        except Exception:
            pass
        try:
            _countdown_timer.stop()
        except Exception:
            logging.exception("Ignored exception in UI init (was except: pass)")

        # Reset UI
        try:
            overlay.stop_recording()
            overlay.hide()
            toolbar.hide()
            toolbar.start_btn.setEnabled(True)
            toolbar.start_btn.setText("Start")
        except Exception:
            pass

        initial.showNormal()
        initial.raise_()
        initial.activateWindow()

    # Shared timer for countdown
    _countdown_timer = QtCore.QTimer()

    # Monitor toolbar visibility during recording. If toolbar disappears unexpectedly
    # while recorder thread is alive, quit the application so the terminal shows exit.
    _visibility_monitor = QtCore.QTimer()
    _visibility_monitor.setInterval(300)

    # Prepare a small context object for monitor callbacks
    class _Ctx:
        pass

    _ctx = _Ctx()
    _ctx.recorder = recorder
    _ctx.toolbar = toolbar
    _ctx.overlay = overlay
    _ctx.visibility_monitor = _visibility_monitor
    _ctx.countdown_timer = _countdown_timer
    _ctx.return_to_main = _return_to_main

    try:
        try:
            _visibility_monitor.timeout.disconnect()
        except Exception:
            pass
        _visibility_monitor.timeout.connect(lambda: monitor_check(_ctx))
    except Exception:
        logging.exception("Failed to connect visibility monitor")

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
            if getattr(recorder, "_thread", None) and recorder._thread.is_alive():
                recorder.stop()
        except Exception:
            logging.exception("Exception while stopping recorder during shutdown")
        try:
            overlay.stop_recording()
        except Exception:
            logging.exception("overlay.stop_recording() failed during shutdown")
        try:
            overlay.hide()
            toolbar.hide()
            initial.hide()
        except Exception:
            logging.exception("Failed hiding windows during shutdown")
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

        # If no selection has been drawn yet, prompt the user to draw one
        try:
            sel_rect = getattr(overlay, "selection_rect", None)
            if not sel_rect or sel_rect.isNull():
                try:
                    # On Windows, prefer a native topmost MessageBox as a fallback.
                    # Some window managers may keep toolbar above Qt dialogs.
                    show_topmost_message(overlay, "提示", "请先按住鼠标左键拖曳绘制矩形框。")
                except Exception:
                    logging.exception("show_topmost_message failed")
                return
        except Exception:
            logging.exception("Exception while handling start click selection check")

        # Start recording immediately (skip countdown)
        try:
            _countdown_timer.stop()
            _countdown_timer.timeout.disconnect()
        except Exception:
            pass
        toolbar.start_btn.setEnabled(False)
        toolbar.start_btn.setText("Recording...")

        # Start recording
        # Use an inset capture region so the overlay's red border isn't recorded
        sel = overlay.get_capture_region(padding=3)
        on_start(sel)
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

        # No default selection: require the user to draw a rectangle before starting

    toolbar.start_requested.connect(_handle_start_clicked)

    def on_stop_clicked():
        # If recorder is active, perform normal stop
        try:
            if getattr(recorder, "_thread", None) and recorder._thread.is_alive():
                return on_stop()
        except Exception:
            pass

        # If the overlay's red selection box is not blinking (not recording),
        # prompt the user to press Start first.
        try:
            if (
                hasattr(overlay, "is_recording_active")
                and not overlay.is_recording_active()
            ):
                try:
                    show_topmost_message(
                        overlay,
                        "提示",
                        "请先按Start按钮开始录制",
                        buttons=QtWidgets.QMessageBox.Ok,
                    )
                except Exception:
                    pass
                return
        except Exception:
            pass

        # Not recording: if overlay is visible but no selection drawn, prompt user
        try:
            sel = getattr(overlay, "selection_rect", None)
            if overlay.isVisible() and (sel is None or sel.isNull()):
                try:
                    ret = show_topmost_message(
                        overlay,
                        "提示",
                        "请先按Start按钮开始录制",
                        buttons=QtWidgets.QMessageBox.Ok,
                    )
                    if ret == QtWidgets.QMessageBox.Ok:
                        try:
                            toolbar.setWindowFlag(QtCore.Qt.WindowStaysOnTopHint, True)
                            toolbar.show()
                            toolbar.raise_()
                            toolbar.activateWindow()
                            try:
                                toolbar.start_btn.setFocus()
                            except Exception:
                                pass
                        except Exception:
                            pass
                except Exception:
                    pass
                return
        except Exception:
            pass

        # Fallback: call on_stop to ensure consistent behavior
        try:
            on_stop()
        except Exception:
            pass

    toolbar.stop_requested.connect(on_stop_clicked)

    def _handle_toolbar_close():
        try:
            # If recording is active: stop and discard recorded content, then return to main
            if getattr(recorder, "_thread", None) and recorder._thread.is_alive():
                try:
                    mp4_path = None
                    try:
                        mp4_path = recorder.stop()
                    except Exception:
                        mp4_path = None
                    # remove temporary mp4 if exists
                    if mp4_path and os.path.exists(mp4_path):
                        try:
                            os.remove(mp4_path)
                        except Exception:
                            pass
                except Exception:
                    pass
                try:
                    _return_to_main()
                except Exception:
                    try:
                        _shutdown_app()
                    except Exception:
                        pass
                return

            # Not recording: return to initial window
            try:
                _return_to_main()
            except Exception:
                try:
                    _shutdown_app()
                except Exception:
                    pass
        except Exception:
            try:
                _shutdown_app()
            except Exception:
                pass

    toolbar.close_requested.connect(_handle_toolbar_close)

    def _enter_record_mode():
        # Reset any previous state
        try:
            _countdown_timer.stop()
        except Exception:
            logging.exception(
                "Ignored exception in finalization block (was except: pass)"
            )
        toolbar.start_btn.setEnabled(True)
        toolbar.start_btn.setText("Start")

        # Show overlay and toolbar when user clicks "录制"
        try:
            overlay.showFullScreen()
            overlay.raise_()
        except Exception:
            overlay.showFullScreen()
        # Set a default centered selection so a red box is visible
        try:
            try:
                screen_geom = QtWidgets.QApplication.primaryScreen().availableGeometry()
                cw, ch = 400, 300
                cx = screen_geom.x() + (screen_geom.width() - cw) // 2
                cy = screen_geom.y() + (screen_geom.height() - ch) // 2
                top_left = overlay.mapFromGlobal(QtCore.QPoint(cx, cy))
                overlay.selection_rect = QtCore.QRect(
                    top_left.x(), top_left.y(), cw, ch
                )
                try:
                    overlay.update_control_handles()
                except Exception:
                    logging.exception(
                        "overlay.update_control_handles failed in _enter_record_mode"
                    )
                try:
                    overlay.update()
                except Exception:
                    pass
            except Exception:
                logging.exception("Failed to create default centered selection")
        except Exception:
            logging.exception("Default selection setup encountered an error")
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

        # No default selection: require the user to draw a rectangle before starting

    initial.record_requested.connect(_enter_record_mode)
    # Keep toolbar above overlay during interactions.
    # Bring to front when overlay emits an interaction.
    try:

        def _bring_toolbar_top():
            try:
                toolbar.raise_()
                toolbar.activateWindow()
                # Ensure toolbar does not overlap the current selection
                try:

                    def _ensure_toolbar_not_overlapping():
                        try:
                            sel = getattr(overlay, "selection_rect", None)
                            if not sel or sel.isNull():
                                return
                            # Map selection rect to global coordinates
                            r = sel.normalized()
                            top_left = overlay.mapToGlobal(r.topLeft())
                            sel_global = QtCore.QRect(top_left, r.size())

                            tb_rect = toolbar.frameGeometry()
                            # Also compute pan handle global rect (if available)
                            pan_global_rect = None
                            try:
                                pan = getattr(overlay, "pan_handle_rect", None)
                                if pan is not None:
                                    pan_tl = overlay.mapToGlobal(pan.topLeft())
                                    pan_global_rect = QtCore.QRect(pan_tl, pan.size())
                            except Exception:
                                pan_global_rect = None

                            # If toolbar intersects neither the selection nor the pan handle, nothing to do
                            if (
                                not sel_global.intersects(tb_rect)
                                and not (pan_global_rect and pan_global_rect.intersects(tb_rect))
                            ):
                                return

                            # Compute screen available geometry and toolbar size
                            try:
                                screen = QtWidgets.QApplication.screenAt(
                                    sel_global.center()
                                )
                            except Exception:
                                screen = QtWidgets.QApplication.primaryScreen()
                            if screen:
                                avail = screen.availableGeometry()
                            else:
                                primary_screen = QtWidgets.QApplication.primaryScreen()
                                avail = primary_screen.availableGeometry()

                            margin = 8
                            tb_w = tb_rect.width()
                            tb_h = tb_rect.height()

                            # Candidate positions: above, right, below, left
                            # (in that priority)
                            candidates = []
                            cx = sel_global.x() + (sel_global.width() - tb_w) // 2
                            # Above
                            min_val = min(
                                cx, avail.x() + avail.width() - tb_w - margin
                            )
                            ax = max(avail.x() + margin, min_val)
                            ay = sel_global.y() - tb_h - margin
                            if ay >= avail.y() + margin:
                                # ensure candidate doesn't overlap pan handle
                                try:
                                    cand_rect = QtCore.QRect(ax, ay, tb_w, tb_h)
                                    if not (pan_global_rect and pan_global_rect.intersects(cand_rect)):
                                        candidates.append(QtCore.QPoint(ax, ay))
                                except Exception:
                                    candidates.append(QtCore.QPoint(ax, ay))
                            # Right
                            rx = sel_global.x() + sel_global.width() + margin
                            min_val2 = min(
                                sel_global.y() + (sel_global.height() - tb_h) // 2,
                                avail.y() + avail.height() - tb_h - margin,
                            )
                            ry = max(avail.y() + margin, min_val2)
                            if rx + tb_w <= avail.x() + avail.width() - margin:
                                try:
                                    cand_rect = QtCore.QRect(rx, ry, tb_w, tb_h)
                                    if not (pan_global_rect and pan_global_rect.intersects(cand_rect)):
                                        candidates.append(QtCore.QPoint(rx, ry))
                                except Exception:
                                    candidates.append(QtCore.QPoint(rx, ry))
                            # Below
                            bx = ax
                            by = sel_global.y() + sel_global.height() + margin
                            if by + tb_h <= avail.y() + avail.height() - margin:
                                try:
                                    cand_rect = QtCore.QRect(bx, by, tb_w, tb_h)
                                    if not (pan_global_rect and pan_global_rect.intersects(cand_rect)):
                                        candidates.append(QtCore.QPoint(bx, by))
                                except Exception:
                                    candidates.append(QtCore.QPoint(bx, by))
                            # Left
                            lx = sel_global.x() - tb_w - margin
                            ly = ry
                            if lx >= avail.x() + margin:
                                try:
                                    cand_rect = QtCore.QRect(lx, ly, tb_w, tb_h)
                                    if not (pan_global_rect and pan_global_rect.intersects(cand_rect)):
                                        candidates.append(QtCore.QPoint(lx, ly))
                                except Exception:
                                    candidates.append(QtCore.QPoint(lx, ly))

                            if candidates:
                                pt = candidates[0]
                            else:
                                pt = QtCore.QPoint(
                                    avail.x() + (avail.width() - tb_w) // 2,
                                    avail.y() + (avail.height() - tb_h) // 2,
                                )

                            try:
                                toolbar.move(pt)
                                try:
                                    toolbar.raise_()
                                    toolbar.activateWindow()
                                except Exception:
                                    pass
                            except Exception:
                                pass

                            # Best-effort: Windows-specific topmost/exclude-from-capture
                            # handling
                            if sys.platform == "win32":
                                try:
                                    from platform_win import (
                                        get_hwnd,
                                        set_window_topmost,
                                        set_exclude_from_capture,
                                    )

                                    tb_hwnd = get_hwnd(toolbar)
                                    if tb_hwnd:
                                        set_window_topmost(tb_hwnd)
                                        try:
                                            set_exclude_from_capture(tb_hwnd, True)
                                        except Exception:
                                            pass
                                except Exception:
                                    pass
                        except Exception:
                            logging.exception("ensure_toolbar_not_overlapping failed")

                    _ensure_toolbar_not_overlapping()
                except Exception:
                    logging.exception(
                        "Toolbar overlap check failed in _bring_toolbar_top"
                    )
                if sys.platform == "win32":
                    try:
                        from platform_win import get_hwnd, set_window_topmost

                        tb_hwnd = get_hwnd(toolbar)
                        if tb_hwnd:
                            set_window_topmost(tb_hwnd)
                    except Exception:
                        logging.exception(
                            "Failed to set toolbar topmost in _bring_toolbar_top"
                        )
            except Exception:
                logging.exception("_bring_toolbar_top encountered an exception")

        overlay.interaction.connect(_bring_toolbar_top)
        try:
            toolbar.moved.connect(_bring_toolbar_top)
        except Exception:
            pass
        # Also ensure toolbar does not overlap selection when entering record mode
        try:

            def _ensure_no_overlap_on_enter():
                try:
                    # reuse bring logic to both raise and avoid overlap
                    _bring_toolbar_top()
                except Exception:
                    logging.exception("_ensure_no_overlap_on_enter failed")

            # call once now to enforce position when entering record mode
            _ensure_no_overlap_on_enter()
        except Exception:
            pass
    except Exception:
        pass
        # On Windows, explicitly adjust Z-order using SetWindowPos.
        # This ensures the toolbar is placed above the overlay.
        try:
            if sys.platform == "win32":
                try:
                    from platform_win import (
                        get_hwnd,
                        set_window_topmost,
                        set_exclude_from_capture,
                        try_set_display_affinity,
                    )

                    ov_hwnd = get_hwnd(overlay)
                    tb_hwnd = get_hwnd(toolbar)
                    if ov_hwnd:
                        set_window_topmost(ov_hwnd)
                    if tb_hwnd:
                        set_window_topmost(tb_hwnd)
                        # Best-effort: exclude toolbar from capture and set affinity
                        set_exclude_from_capture(tb_hwnd, True)
                        try_set_display_affinity(tb_hwnd)
                except Exception:
                    logging.exception("Windows Z-order/DWM setup failed during startup")
        except Exception:
            logging.exception("Unexpected error in startup platform logic")
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
            with open(trace_path, "a", encoding="utf-8") as tf:
                tf.write(f"app.exec_ returned {rc}\n")
        except Exception:
            pass
        sys.exit(rc)
    except Exception as e:
        try:
            with open(trace_path, "a", encoding="utf-8") as tf:
                tf.write(f"app.exec_ raised: {e}\n")
        except Exception:
            pass
        raise


if __name__ == "__main__":
    main()
