from PyQt5 import QtWidgets, QtCore


class ToolBar(QtWidgets.QWidget):
    start_requested = QtCore.pyqtSignal()
    stop_requested = QtCore.pyqtSignal()
    cancel_requested = QtCore.pyqtSignal()

    def __init__(self):
        super().__init__()
        self.setWindowFlags(QtCore.Qt.Tool | QtCore.Qt.WindowStaysOnTopHint)
        self.setWindowTitle('Screen2GIF')
        layout = QtWidgets.QHBoxLayout()
        self.start_btn = QtWidgets.QPushButton('Start')
        self.stop_btn = QtWidgets.QPushButton('Stop')
        self.cancel_btn = QtWidgets.QPushButton('Cancel')
        layout.addWidget(self.start_btn)
        layout.addWidget(self.stop_btn)
        layout.addWidget(self.cancel_btn)
        self.setLayout(layout)

        self.start_btn.clicked.connect(self.start_requested.emit)
        self.stop_btn.clicked.connect(self.stop_requested.emit)
        self.cancel_btn.clicked.connect(self.cancel_requested.emit)
