from PyQt5 import QtWidgets, QtCore, QtGui


class OverlayWindow(QtWidgets.QWidget):
    interaction = QtCore.pyqtSignal()
    def __init__(self):
        super().__init__()
        # Keep overlay frameless and make it stay on top of normal windows
        flags = QtCore.Qt.FramelessWindowHint | QtCore.Qt.WindowStaysOnTopHint | QtCore.Qt.Window
        self.setWindowFlags(flags)
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground)

        self.selection_rect = None  # QRect or None
        self._dragging_handle = None  # index 0-7 for control handles, or None
        self._drag_offset = None
        self.handle_size = 8
        self.control_handles = []  # list of QRect for handles

        # For drawing new selection
        self._start_pos = None

        # Recording indicator (blinking)
        self.is_recording = False
        self._blink_visible = True
        self._blink_timer = QtCore.QTimer(self)
        self._blink_timer.setInterval(500)
        self._blink_timer.timeout.connect(self._toggle_blink)

    def _toggle_blink(self):
        self._blink_visible = not self._blink_visible
        self.update()

    def start_recording(self):
        self.is_recording = True
        self._blink_visible = True
        self._blink_timer.start()
        self.update()

    def stop_recording(self):
        self.is_recording = False
        self._blink_timer.stop()
        self._blink_visible = True
        self.update()

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)

        # full overlay (60% translucent black)
        overlay_color = QtGui.QColor(0, 0, 0, int(255 * 0.6))
        # draw full-screen translucent overlay
        painter.fillRect(self.rect(), overlay_color)

        # clear the selection area from the overlay so underlying content shows through
        if self.selection_rect and not self.selection_rect.isNull():
            rectf = QtCore.QRectF(self.selection_rect)
            # set composition mode to Clear to make selection area transparent
            painter.setCompositionMode(QtGui.QPainter.CompositionMode_Clear)
            painter.fillRect(rectf, QtCore.Qt.transparent)
            # restore composition mode for drawing border/handles
            painter.setCompositionMode(QtGui.QPainter.CompositionMode_SourceOver)

            # selection border (red). Blink when recording
            pen = QtGui.QPen(QtGui.QColor(255, 0, 0))
            pen.setWidth(2)
            painter.setPen(pen)
            if not self.is_recording or (self.is_recording and self._blink_visible):
                painter.drawRect(rectf)

            # draw control handles
            self.update_control_handles()
            brush = QtGui.QBrush(QtGui.QColor(255, 255, 255))
            pen2 = QtGui.QPen(QtGui.QColor(0, 0, 0))
            painter.setBrush(brush)
            painter.setPen(pen2)
            for h in self.control_handles:
                painter.drawRect(QtCore.QRectF(h))

    def mousePressEvent(self, event):
        if event.button() != QtCore.Qt.LeftButton:
            return
        pos = event.pos()

        # check if clicking a control handle
        for idx, h in enumerate(self.control_handles):
            if h.contains(pos):
                self._dragging_handle = idx
                self._drag_offset = pos
                return

        # start new selection
        self._start_pos = pos
        self.selection_rect = QtCore.QRect(pos, pos)
        try:
            self.interaction.emit()
        except Exception:
            pass
        self.update()

    def mouseMoveEvent(self, event):
        pos = event.pos()
        if self._dragging_handle is not None and self.selection_rect:
            # adjust selection_rect based on which handle is dragged
            r = QtCore.QRect(self.selection_rect)
            idx = self._dragging_handle
            x1 = r.left()
            y1 = r.top()
            x2 = r.right()
            y2 = r.bottom()

            if idx == 0:  # NW
                x1 = pos.x()
                y1 = pos.y()
            elif idx == 1:  # N
                y1 = pos.y()
            elif idx == 2:  # NE
                x2 = pos.x()
                y1 = pos.y()
            elif idx == 3:  # E
                x2 = pos.x()
            elif idx == 4:  # SE
                x2 = pos.x()
                y2 = pos.y()
            elif idx == 5:  # S
                y2 = pos.y()
            elif idx == 6:  # SW
                x1 = pos.x()
                y2 = pos.y()
            elif idx == 7:  # W
                x1 = pos.x()

            newr = QtCore.QRect(QtCore.QPoint(min(x1, x2), min(y1, y2)), QtCore.QPoint(max(x1, x2), max(y1, y2)))
            self.selection_rect = newr
            self.update()
            return

        if self._start_pos:
            self.selection_rect = QtCore.QRect(self._start_pos, pos).normalized()
            try:
                self.interaction.emit()
            except Exception:
                pass
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() != QtCore.Qt.LeftButton:
            return
        # end dragging or selection
        self._dragging_handle = None
        self._drag_offset = None
        self._start_pos = None
        if self.selection_rect:
            self.selection_rect = self.selection_rect.normalized()
            self.update_control_handles()
        try:
            self.interaction.emit()
        except Exception:
            pass
        self.update()

    def update_control_handles(self):
        self.control_handles = []
        if not self.selection_rect or self.selection_rect.isNull():
            return
        r = self.selection_rect
        cx = (r.left() + r.right()) // 2
        cy = (r.top() + r.bottom()) // 2
        s = self.handle_size

        points = [
            (r.left(), r.top()),
            (cx, r.top()),
            (r.right(), r.top()),
            (r.right(), cy),
            (r.right(), r.bottom()),
            (cx, r.bottom()),
            (r.left(), r.bottom()),
            (r.left(), cy),
        ]
        for (px, py) in points:
            self.control_handles.append(QtCore.QRect(px - s // 2, py - s // 2, s, s))

    def get_selection(self):
        if not self.selection_rect or self.selection_rect.isNull():
            geom = QtWidgets.QApplication.primaryScreen().geometry()
            return (geom.x(), geom.y(), geom.width(), geom.height())
        r = self.selection_rect.normalized()
        # Map widget-local coordinates to global/screen coordinates
        top_left = self.mapToGlobal(r.topLeft())
        return (top_left.x(), top_left.y(), r.width(), r.height())

    def get_capture_region(self, padding=3):
        """Return a capture region inset by padding pixels to avoid overlay border.

        Returns (x, y, w, h) in global/screen coordinates.
        """
        x, y, w, h = self.get_selection()
        # Inset the rectangle by padding on all sides
        nx = x + padding
        ny = y + padding
        nw = max(1, w - 2 * padding)
        nh = max(1, h - 2 * padding)
        return (nx, ny, nw, nh)
