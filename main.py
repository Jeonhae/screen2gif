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
                logging.exception("Failed to restore toolbar focus after message")

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
        if recorder.is_recording():
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


class GifConversionWorker(QtCore.QObject):
    """Background worker: convert MP4 to GIF and shrink to target size."""

    finished = QtCore.pyqtSignal(dict)

    def __init__(self, mp4_path: str, target_bytes: int):
        super().__init__()
        self._mp4_path = mp4_path
        self._target_bytes = target_bytes

    @QtCore.pyqtSlot()
    def run(self):
        result = {"ok": False, "gif_path": None, "error": "Unknown conversion error"}
        try:
            _removed, clear_errors = clear_gif_folder()
            if clear_errors:
                logging.warning(
                    "clear_gif_folder had %d error(s): %s",
                    len(clear_errors),
                    clear_errors[:3],
                )
            gif_path = timestamped_filename("gif", "gif")
            ok = convert_mp4_to_gif(self._mp4_path, gif_path, fps=10)
            if not ok:
                result["error"] = "Failed to convert to GIF"
                self.finished.emit(result)
                return

            small_dir = os.path.join(os.path.dirname(__file__), "smallGif")
            orig_size = os.path.getsize(gif_path)
            if orig_size <= self._target_bytes:
                os.makedirs(small_dir, exist_ok=True)
                dst = os.path.join(small_dir, os.path.basename(gif_path))
                shutil.copy2(gif_path, dst)
                final_path = dst
            else:
                shrunk = shrink_gif_to_target(
                    gif_path,
                    self._target_bytes,
                    small_dir,
                    source_mp4_path=self._mp4_path,
                )
                final_path = shrunk or gif_path

            result = {"ok": True, "gif_path": final_path, "error": None}
        except Exception as e:
            logging.exception("GIF conversion worker failed")
            result["error"] = str(e)
        self.finished.emit(result)


class MainThreadDispatcher(QtCore.QObject):
    """Bridge worker-thread completion into the GUI thread explicitly."""

    conversion_result = QtCore.pyqtSignal(dict)

    @QtCore.pyqtSlot(dict)
    def forward_conversion_result(self, result: dict):
        self.conversion_result.emit(result)


def _finalize_conversion_result(ctx, result):
    """Handle conversion result on the main/UI thread."""
    thread = getattr(ctx, "conversion_thread", None)
    ctx.conversion_in_progress = False
    try:
        if thread and thread.isRunning():
            thread.quit()
            thread.wait(2000)
    except Exception:
        logging.exception("Failed to stop conversion thread")
    finally:
        ctx.conversion_worker = None
        ctx.conversion_thread = None

    try:
        if result.get("ok") and result.get("gif_path"):
            gif_path = result["gif_path"]
            copied_ok = bool(copy_path_to_clipboard(gif_path))
            if copied_ok:
                show_topmost_message(
                    None,
                    "Success",
                    "GIF generated and copied to clipboard.\n"
                    f"Path: {gif_path}\nPress Ctrl+V to paste.",
                    icon=QtWidgets.QMessageBox.Information,
                )
            else:
                show_topmost_message(
                    None,
                    "GIF generated",
                    "GIF generated, but failed to copy to clipboard.\n"
                    f"Path: {gif_path}",
                    icon=QtWidgets.QMessageBox.Warning,
                )
        else:
            err_text = result.get("error") or "Failed to convert to GIF"
            show_topmost_message(
                None,
                "Error",
                err_text,
                icon=QtWidgets.QMessageBox.Warning,
            )
    except Exception:
        logging.exception("Failed to finalize conversion result in UI")
    finally:
        try:
            ctx.return_to_main()
        except Exception:
            logging.exception("return_to_main failed at end of stop_recording_flow")


def start_recording_flow(ctx, rect):
    """Module-level flow to start recording given a context and selection rect.

    `ctx` is expected to provide: `overlay`, `toolbar`, `recorder`,
    `visibility_monitor`, and `return_to_main` (callable).
    """
    overlay = ctx.overlay
    toolbar = ctx.toolbar
    recorder = ctx.recorder
    visibility_monitor = ctx.visibility_monitor

    if getattr(ctx, "conversion_in_progress", False):
        show_topmost_message(
            None,
            "Please wait",
            "GIF is still being processed. Try again after conversion finishes.",
            icon=QtWidgets.QMessageBox.Information,
        )
        return

    x, y, w, h = rect
    output_mp4 = timestamped_filename("video", "mp4")

    # Ensure video output folder is clean before writing a new recording.
    try:
        _removed, clear_errors = clear_video_folder()
        if clear_errors:
            logging.warning(
                "clear_video_folder had %d error(s): %s",
                len(clear_errors),
                clear_errors[:3],
            )
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
                logging.exception("_process_ui_events_wait failed in start_flow")
    except Exception:
        logging.exception("Unexpected error in start_recording_flow platform logic")

    try:
        overlay.start_recording()
    except Exception:
        logging.exception("overlay.start_recording failed in start_recording_flow")

    try:
        started = recorder.start(
            (x, y, w, h),
            fps=10,
            out_path=output_mp4,
            startup_timeout=3.0,
        )
        if (not started) and recorder.is_recording():
            logging.warning(
                "Recorder startup returned False but thread is recording; continuing"
            )
            started = True
        _process_ui_events_wait(120)
        if (not started) or (not recorder.is_recording()):
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

    if getattr(ctx, "conversion_in_progress", False):
        show_topmost_message(
            None,
            "Please wait",
            "GIF is still being processed. Please wait until it completes.",
            icon=QtWidgets.QMessageBox.Information,
        )
        return

    if not recorder.is_recording():
        show_topmost_message(
            None,
            "Not recording",
            "No active recording to stop. Please click Start first.",
            icon=QtWidgets.QMessageBox.Information,
        )
        try:
            ctx.return_to_main()
        except Exception:
            logging.exception("return_to_main failed when stop clicked while idle")
        return

    mp4_path, stopped_ok = recorder.stop(timeout=5.0)
    try:
        visibility_monitor.stop()
    except Exception:
        logging.exception("visibility_monitor.stop failed in stop_recording_flow")

    try:
        overlay.stop_recording()
    except Exception:
        logging.exception("overlay.stop_recording failed in stop_recording_flow")
    try:
        # Save current selection so next round can reuse it (same process only)
        try:
            sel = getattr(overlay, "selection_rect", None)
            if sel is not None and (not getattr(sel, "isNull", lambda: False)()):
                try:
                    ctx.last_selection_rect = sel
                except Exception:
                    logging.exception("Failed saving last selection rect in stop_recording_flow")
        except Exception:
            logging.exception("Failed to capture selection before hiding UI in stop_recording_flow")

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

    if not stopped_ok:
        show_topmost_message(
            None,
            "Error",
            (
                "Recorder did not stop cleanly. Conversion was skipped "
                "to avoid corrupted GIF output."
            ),
            icon=QtWidgets.QMessageBox.Warning,
        )
        try:
            ctx.return_to_main()
        except Exception:
            logging.exception("return_to_main failed after recorder stop timeout")
        return

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

    ctx.conversion_in_progress = True

    worker = GifConversionWorker(mp4_path, DEFAULT_GIF_TARGET_BYTES)
    thread = QtCore.QThread()
    worker.moveToThread(thread)
    ctx.conversion_worker = worker
    ctx.conversion_thread = thread

    worker.finished.connect(
        ctx.dispatcher.forward_conversion_result,
        QtCore.Qt.QueuedConnection,
    )
    worker.finished.connect(worker.deleteLater)
    thread.finished.connect(thread.deleteLater)
    thread.started.connect(worker.run)
    thread.start()


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
            if recorder.is_recording():
                recorder.request_stop()
                if not recorder.wait_stopped(timeout=1.0):
                    logging.warning("Recorder did not stop cleanly during aboutToQuit")
        except Exception:
            logging.exception("Failed while stopping recorder in aboutToQuit")
        try:
            t = getattr(_ctx, "conversion_thread", None)
            if t and t.isRunning():
                t.quit()
                t.wait(2000)
        except Exception:
            logging.exception("Failed stopping conversion thread in aboutToQuit")
        try:
            _visibility_monitor.stop()
        except Exception:
            logging.exception("Failed to stop visibility monitor in aboutToQuit")

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
            # Protect against invoking stop/conversion when not actively recording.
            try:
                if not (_ctx.recorder and _ctx.recorder.is_recording()):
                    try:
                        show_topmost_message(
                            None,
                            "Not recording",
                            "No active recording to stop. Please click Start first.",
                            icon=QtWidgets.QMessageBox.Information,
                        )
                    except Exception:
                        logging.exception("show_topmost_message failed in on_stop")
                    return
            except Exception:
                logging.exception("Failed checking recorder state in on_stop")

            stop_recording_flow(_ctx)
        except Exception:
            logging.exception("stop_recording_flow raised in on_stop")

    # Initial launcher window
    class InitialWindow(QtWidgets.QWidget):
        record_requested = QtCore.pyqtSignal()

        def __init__(self):
            super().__init__()
            self.setObjectName("Screen2GIFInitialWindow")
            self.setWindowTitle("Screen2GIF")
            # Use a normal window so it reliably appears (not a tool window)
            self.setWindowFlags(QtCore.Qt.Window | QtCore.Qt.WindowStaysOnTopHint)
            # Disable the maximize button for this initial launcher window
            try:
                self.setWindowFlag(QtCore.Qt.WindowMaximizeButtonHint, False)
            except Exception:
                logging.exception("Failed to disable maximize button on initial window")
            layout = QtWidgets.QVBoxLayout()
            # author/credit label above the main instruction
            try:
                self.by_label = QtWidgets.QLabel("By 译路同行")
                self.by_label.setAlignment(QtCore.Qt.AlignCenter)
                layout.addWidget(self.by_label)
            except Exception:
                logging.exception("Failed to initialize author label")
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
    # Remember the last selection rectangle during this app session.
    # Stored as global coords tuple: (x, y, w, h).
    _last_selection_rect_global = [None]

    def _return_to_main():
        # Stop any active recording/countdown
        # If application is in shutdown, don't reopen the initial window
        try:
            inst = QtWidgets.QApplication.instance()
            if inst and inst.closingDown():
                return
        except Exception:
            logging.exception("Failed to inspect app closing state in return_to_main")
        if recorder.is_recording():
            _, stopped_ok = recorder.stop(timeout=2.0)
            if not stopped_ok:
                logging.warning("Recorder did not stop cleanly in return_to_main")
        try:
            _visibility_monitor.stop()
        except Exception:
            logging.exception("Failed stopping visibility monitor in return_to_main")
        try:
            _countdown_timer.stop()
        except Exception:
            logging.exception("Ignored exception in UI init (was except: pass)")

        # Reset UI
        try:
            overlay.stop_recording()
            try:
                sel = getattr(overlay, "selection_rect", None)
                if sel and not sel.isNull():
                    r = sel.normalized()
                    tl = overlay.mapToGlobal(r.topLeft())
                    _last_selection_rect_global[0] = (
                        int(tl.x()),
                        int(tl.y()),
                        int(r.width()),
                        int(r.height()),
                    )
            except Exception:
                logging.exception("Failed to persist last selection rectangle")
            overlay.hide()
            toolbar.hide()
            toolbar.start_btn.setEnabled(True)
            toolbar.start_btn.setText("Start")
        except Exception:
            logging.exception("Failed resetting UI state in return_to_main")

        initial.showNormal()
        initial.raise_()
        initial.activateWindow()

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
    _ctx.conversion_in_progress = False
    _ctx.conversion_worker = None
    _ctx.conversion_thread = None
    # Store last used selection rect between rounds within same process
    _ctx.last_selection_rect = None
    _ctx.dispatcher = MainThreadDispatcher()
    _ctx.dispatcher.conversion_result.connect(
        lambda result: _finalize_conversion_result(_ctx, result)
    )

    try:
        try:
            _visibility_monitor.timeout.disconnect()
        except Exception:
            logging.exception("Failed to disconnect visibility monitor timeout")
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
            logging.exception("Failed to stop countdown timer during shutdown")
        try:
            _visibility_monitor.stop()
        except Exception:
            logging.exception("Failed to stop visibility monitor during shutdown")
        try:
            if recorder.is_recording():
                _, stopped_ok = recorder.stop(timeout=2.0)
                if not stopped_ok:
                    logging.warning("Recorder did not stop cleanly during shutdown")
        except Exception:
            logging.exception("Exception while stopping recorder during shutdown")
        try:
            overlay.stop_recording()
        except Exception:
            logging.exception("overlay.stop_recording() failed during shutdown")
        try:
            t = _ctx.conversion_thread
            if t and t.isRunning():
                t.quit()
                t.wait(2000)
            _ctx.conversion_in_progress = False
        except Exception:
            logging.exception("Failed stopping conversion thread during shutdown")
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
                logging.exception("Failed to exit process during shutdown")

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
                    show_topmost_message(
                        overlay,
                        "提示",
                        "请先按住鼠标左键拖曳绘制矩形框。",
                    )
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
            logging.exception("Failed to reset countdown timer on start click")
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
            logging.exception("Failed to show/activate toolbar on start")
        # hide the initial launcher window
        try:
            initial.hide()
        except Exception:
            logging.exception("Failed to hide initial window on start")

        # No default selection: require the user to draw a rectangle before starting

    toolbar.start_requested.connect(_handle_start_clicked)

    def on_stop_clicked():
        # If recorder is active, perform normal stop
        try:
            if recorder.is_recording():
                return on_stop()
        except Exception:
            logging.exception("Failed checking recorder state in on_stop_clicked")

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
                    logging.exception("Failed to show stop hint message")
                return
        except Exception:
            logging.exception("Failed to check recording-active state on stop")

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
                                logging.exception("Failed to focus start button")
                        except Exception:
                            logging.exception(
                                "Failed to reactivate toolbar on stop hint"
                            )
                except Exception:
                    logging.exception("Failed to show stop hint dialog")
                return
        except Exception:
            logging.exception("Failed to validate selection state on stop")

        # Fallback: explicitly avoid stop flow when idle.
        # This prevents reusing stale recorder output paths from older runs.
        try:
            show_topmost_message(
                overlay,
                "提示",
                "当前未在录制，请先按Start按钮开始录制",
                buttons=QtWidgets.QMessageBox.Ok,
            )
        except Exception:
            logging.exception("Fallback idle stop hint failed")

    toolbar.stop_requested.connect(on_stop_clicked)

    def _handle_toolbar_close():
        try:
            # If recording is active, stop and discard recorded content,
            # then return to main.
            if recorder.is_recording():
                try:
                    mp4_path = None
                    try:
                        mp4_path, _ = recorder.stop(timeout=2.0)
                    except Exception:
                        mp4_path = None
                    # remove temporary mp4 if exists
                    if mp4_path and os.path.exists(mp4_path):
                        try:
                            os.remove(mp4_path)
                        except Exception:
                            logging.exception("Failed removing temporary mp4 on close")
                except Exception:
                    logging.exception("Failed to stop recorder during toolbar close")
                try:
                    _return_to_main()
                except Exception:
                    try:
                        _shutdown_app()
                    except Exception:
                        logging.exception(
                            "Failed to shutdown after close while recording"
                        )
                return

            # Not recording: return to initial window
            try:
                _return_to_main()
            except Exception:
                try:
                    _shutdown_app()
                except Exception:
                    logging.exception("Failed to shutdown after close while idle")
        except Exception:
            try:
                _shutdown_app()
            except Exception:
                logging.exception("Failed to shutdown app after toolbar close error")

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
                restored = False
                last_rect = _last_selection_rect_global[0]
                if last_rect:
                    try:
                        gx, gy, gw, gh = last_rect
                        if gw > 0 and gh > 0:
                            top_left = overlay.mapFromGlobal(QtCore.QPoint(gx, gy))
                            overlay.selection_rect = QtCore.QRect(
                                int(top_left.x()),
                                int(top_left.y()),
                                int(gw),
                                int(gh),
                            )
                            restored = True
                    except Exception:
                        logging.exception("Failed to restore last selection rectangle")
                        restored = False
                if not restored:
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
                    logging.exception("overlay.update failed in _enter_record_mode")
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
            logging.exception("Failed to show toolbar in _enter_record_mode")
        # hide the initial launcher window
        try:
            initial.hide()
        except Exception:
            logging.exception("Failed to hide initial window in _enter_record_mode")

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

                            # If toolbar intersects neither selection nor pan handle,
                            # no repositioning is needed.
                            if (
                                not sel_global.intersects(tb_rect)
                                and not (
                                    pan_global_rect
                                    and pan_global_rect.intersects(tb_rect)
                                )
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
                                    if not (
                                        pan_global_rect
                                        and pan_global_rect.intersects(cand_rect)
                                    ):
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
                                    if not (
                                        pan_global_rect
                                        and pan_global_rect.intersects(cand_rect)
                                    ):
                                        candidates.append(QtCore.QPoint(rx, ry))
                                except Exception:
                                    candidates.append(QtCore.QPoint(rx, ry))
                            # Below
                            bx = ax
                            by = sel_global.y() + sel_global.height() + margin
                            if by + tb_h <= avail.y() + avail.height() - margin:
                                try:
                                    cand_rect = QtCore.QRect(bx, by, tb_w, tb_h)
                                    if not (
                                        pan_global_rect
                                        and pan_global_rect.intersects(cand_rect)
                                    ):
                                        candidates.append(QtCore.QPoint(bx, by))
                                except Exception:
                                    candidates.append(QtCore.QPoint(bx, by))
                            # Left
                            lx = sel_global.x() - tb_w - margin
                            ly = ry
                            if lx >= avail.x() + margin:
                                try:
                                    cand_rect = QtCore.QRect(lx, ly, tb_w, tb_h)
                                    if not (
                                        pan_global_rect
                                        and pan_global_rect.intersects(cand_rect)
                                    ):
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
            logging.exception("Failed to connect toolbar.moved handler")
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
            logging.exception("Failed to run initial no-overlap placement")
    except Exception:
        logging.exception("Failed to wire toolbar/overlay interaction handlers")
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
