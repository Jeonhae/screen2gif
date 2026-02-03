import os

new_content = r'''import sys
import traceback
import os
import time

# -----------------------------------------------------------------------------
# 1. Crash Logger Setup
#    Captures early import errors or runtime crashes to 'crash_error.log'
# -----------------------------------------------------------------------------
log_dir = os.path.join(os.path.dirname(__file__), 'logs')
os.makedirs(log_dir, exist_ok=True)
crash_log = os.path.join(log_dir, 'crash_error.log')

def _log_exception(etype, value, tb):
    with open(crash_log, 'w', encoding='utf-8') as f:
        f.write(f"Timestamp: {time.time()}\n")
        f.write("".join(traceback.format_exception(etype, value, tb)))
    # Allow default PyQt handling to also print if possible
    sys.__excepthook__(etype, value, tb)

sys.excepthook = _log_exception

# -----------------------------------------------------------------------------
# 2. Imports
# -----------------------------------------------------------------------------
try:
    from PyQt5 import QtWidgets, QtCore
    from overlay import OverlayWindow
    from toolbar import ToolBar
    from recorder import ScreenRecorder
    from converter import convert_mp4_to_gif
    from clipboard_clean import copy_path_to_clipboard
    from utils import ensure_dirs, timestamped_filename
except Exception:
    # If imports fail, this will catch it and log it via sys.excepthook
    raise

# -----------------------------------------------------------------------------
# 3. Launcher Window Class
# -----------------------------------------------------------------------------
class InitialWindow(QtWidgets.QWidget):
    record_requested = QtCore.pyqtSignal()

    def __init__(self):
        super().__init__()
        self.setWindowTitle('Screen2GIF')
        self.resize(300, 150)
        
        # Center the window
        screen_geo = QtWidgets.QApplication.primaryScreen().availableGeometry()
        x = screen_geo.x() + (screen_geo.width() - self.width()) // 2
        y = screen_geo.y() + (screen_geo.height() - self.height()) // 2
        self.move(x, y)

        layout = QtWidgets.QVBoxLayout()
        
        label = QtWidgets.QLabel('点击下面的按钮进入录制模式')
        label.setAlignment(QtCore.Qt.AlignCenter)
        
        self.btn_record = QtWidgets.QPushButton('录制')
        self.btn_record.setMinimumHeight(40)
        self.btn_record.clicked.connect(self.record_requested.emit)
        
        layout.addWidget(label)
        layout.addWidget(self.btn_record)
        self.setLayout(layout)

# -----------------------------------------------------------------------------
# 4. Main Application Logic
# -----------------------------------------------------------------------------
def main():
    ensure_dirs()
    
    # Enable High DPI scaling
    if hasattr(QtCore.Qt, 'AA_EnableHighDpiScaling'):
        QtWidgets.QApplication.setAttribute(QtCore.Qt.AA_EnableHighDpiScaling, True)
    if hasattr(QtCore.Qt, 'AA_UseHighDpiPixmaps'):
        QtWidgets.QApplication.setAttribute(QtCore.Qt.AA_UseHighDpiPixmaps, True)

    app = QtWidgets.QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False) # Important because we toggle windows
    
    # Components
    initial_window = InitialWindow()
    overlay = OverlayWindow()
    toolbar = ToolBar()
    recorder = ScreenRecorder()

    # --- Logic: Transition from Launcher to Overlay ---
    def enter_recording_mode():
        initial_window.hide()
        
        # Show Overlay (Fullscreen transparent)
        overlay.showFullScreen()
        
        # Default Selection Center
        screen_geo = QtWidgets.QApplication.primaryScreen().geometry()
        cw, ch = 400, 300
        cx = screen_geo.x() + (screen_geo.width() - cw) // 2
        cy = screen_geo.y() + (screen_geo.height() - ch) // 2
        
        # Map to overlay coordinates
        top_left = overlay.mapFromGlobal(QtCore.QPoint(cx, cy))
        overlay.selection_rect = QtCore.QRect(top_left.x(), top_left.y(), cw, ch)
        try:
            overlay.update_control_handles()
        except:
             pass
        
        # Show Toolbar
        toolbar.showNormal()
        toolbar.raise_()
        toolbar.activateWindow()
        
        # Ensure toolbar stays on top
        toolbar.setWindowFlag(QtCore.Qt.WindowStaysOnTopHint, True)
        toolbar.show()

    initial_window.record_requested.connect(enter_recording_mode)

    # --- Logic: Start Recording (triggered by Toolbar) ---
    def start_recording_action():
        if not overlay.isVisible():
            # Show overlay if hidden
            overlay.showFullScreen()
            return
            
        region = overlay.get_capture_region()
        if not region:
            return
            
        x, y, w, h = region
        
        # Start backend
        output_mp4 = timestamped_filename('video', 'mp4')
        
        # Lock visual state
        overlay.start_recording()
        
        # Start recorder
        recorder.start((x, y, w, h), fps=10, out_path=output_mp4)

    toolbar.start_requested.connect(start_recording_action)

    # --- Logic: Stop Recording ---
    def stop_recording_action():
        mp4_path = recorder.stop()
        overlay.stop_recording()
        overlay.hide()
        
        if not mp4_path:
            QtWidgets.QMessageBox.warning(None, 'Error', 'No recording produced')
            return

        # Convert to GIF
        gif_path = timestamped_filename('gif', 'gif')
        ok = convert_mp4_to_gif(mp4_path, gif_path, fps=10)
        
        if ok:
            copy_path_to_clipboard(gif_path)
            QtWidgets.QMessageBox.information(None, 'Done', f'GIF saved and copied:\n{gif_path}')
        else:
            QtWidgets.QMessageBox.warning(None, 'Error', 'GIF Conversion Failed')

    toolbar.stop_requested.connect(stop_recording_action)

    # --- Logic: Cancel ---
    def cancel_action():
        if getattr(recorder, '_thread', None) and recorder._thread.is_alive():
            recorder.stop()
        
        overlay.stop_recording()
        overlay.hide()
        
        # Quit as per requirement
        app.quit()

    toolbar.cancel_requested.connect(cancel_action)

    # Show initial window
    initial_window.show()
    initial_window.raise_()
    initial_window.activateWindow()

    sys.exit(app.exec_())

if __name__ == '__main__':
    main()
'''

target_file = os.path.join(os.path.dirname(__file__), 'main.py')
with open(target_file, 'w', encoding='utf-8') as f:
    f.write(new_content)

print("Patcher finished.")
