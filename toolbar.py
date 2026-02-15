from PyQt5 import QtWidgets
from PyQt5 import QtCore
import logging


class ToolBar(QtWidgets.QWidget):
    start_requested = QtCore.pyqtSignal()
    stop_requested = QtCore.pyqtSignal()
    close_requested = QtCore.pyqtSignal()
    moved = QtCore.pyqtSignal()

    def __init__(self):
        super().__init__()
        self.setWindowFlags(
            QtCore.Qt.Tool
            | QtCore.Qt.WindowStaysOnTopHint
            | QtCore.Qt.WindowCloseButtonHint
        )
        self.setWindowTitle("Screen2GIF")
        layout = QtWidgets.QHBoxLayout()
        self.start_btn = QtWidgets.QPushButton("Start")
        self.stop_btn = QtWidgets.QPushButton("Stop")
        layout.addWidget(self.start_btn)
        layout.addWidget(self.stop_btn)
        self.setLayout(layout)

        # Start immediately when clicked.
        self.start_btn.clicked.connect(self.start_requested.emit)
        self.stop_btn.clicked.connect(self.stop_requested.emit)

        # Periodically enforce top-most state so toolbar stays above overlays
        self._top_timer = QtCore.QTimer(self)
        self._top_timer.setInterval(300)
        self._top_timer.timeout.connect(self._ensure_on_top)
        self._top_timer.start()

    def _ensure_on_top(self):
        try:
            # Reapply the stay-on-top flag and raise the window
            flags = int(self.windowFlags())
            if not (flags & int(QtCore.Qt.WindowStaysOnTopHint)):
                self.setWindowFlags(flags | int(QtCore.Qt.WindowStaysOnTopHint))
                # show() needed to apply new flags on some platforms
                self.show()
            try:
                self.raise_()
            except Exception:
                logging.exception("Failed to raise toolbar window")
        except Exception:
            logging.exception("Failed to enforce toolbar top-most state")

    def moveEvent(self, event):
        try:
            super().moveEvent(event)
        except Exception:
            logging.exception("super().moveEvent failed")
        try:
            # Emit a moved signal so external logic can react.
            # This lets external code avoid overlapping the selection.
            self.moved.emit()
        except Exception:
            logging.exception("Failed to emit moved signal")

    def closeEvent(self, event):
        # Emit signal so main app can handle UI/state reset.
        # Let the main app decide whether to save/stop/quit.
        # Do NOT call QApplication.quit() here; let the main handler
        # control application shutdown.
        try:
            self.close_requested.emit()
        except Exception:
            logging.exception("Failed to emit close_requested signal")
        try:
            event.accept()
        except Exception:
            logging.exception("Failed to accept toolbar close event")

    # Countdown logic removed: Start triggers immediately.
