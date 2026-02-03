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
        # Allow clicks to pass through so the user can interact with apps while recording
        try:
            self.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents, True)
        except Exception:
            pass
        self._blink_timer.start()
        self.update()

    def stop_recording(self):
        self.is_recording = False
        self._blink_timer.stop()
        self._blink_visible = True
        try:
            self.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents, False)
        except Exception:
            pass
        self.update()

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)

        # Dim the screen only during selection; keep it fully transparent while recording
        if not self.is_recording:
            overlay_color = QtGui.QColor(0, 0, 0, int(255 * 0.3))
            painter.fillRect(self.rect(), overlay_color)
        else:
            painter.fillRect(self.rect(), QtCore.Qt.transparent)

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
        # Determine which QScreen contains the selection (logical coords)
        try:
            screen = QtWidgets.QApplication.screenAt(QtCore.QPoint(int(nx), int(ny)))
            if screen is None:
                screen = QtWidgets.QApplication.primaryScreen()

            # devicePixelRatio may be float (1.0, 1.25, 1.5...) depending on Qt build
            try:
                # prefer devicePixelRatioF if available
                dpr = float(screen.devicePixelRatioF()) if hasattr(screen, 'devicePixelRatioF') else float(screen.devicePixelRatio())
            except Exception:
                dpr = float(self.devicePixelRatioF() if hasattr(self, 'devicePixelRatioF') else 1.0)

            # Map logical selection relative to screen logical origin, then scale to physical pixels
            sgeom = screen.geometry()
            logical_origin_x = sgeom.x()
            logical_origin_y = sgeom.y()

            # On Windows/Qt the screen origin is often already in physical pixels even when
            # width/height are logical, so start with the unscaled origin.
            phys_origin_x = int(round(logical_origin_x))
            phys_origin_y = int(round(logical_origin_y))
            scaled_origin_x = int(round(logical_origin_x * dpr))
            scaled_origin_y = int(round(logical_origin_y * dpr))

            # Try to find matching physical monitor via mss to get accurate physical origin
            try:
                import mss as _mss
                mons = _mss.mss().monitors
                matched = None
                for m in mons[1:]:
                    try:
                        m_left = int(m.get('left', 0))
                        m_top = int(m.get('top', 0))
                    except Exception:
                        continue
                    # First try matching against the unscaled origin; fall back to scaled comparison
                    if abs(m_left - phys_origin_x) < 4 and abs(m_top - phys_origin_y) < 4:
                        matched = m
                        break
                    if abs(m_left - scaled_origin_x) < 4 and abs(m_top - scaled_origin_y) < 4:
                        matched = m
                        break
                if matched:
                    phys_origin_x = int(matched.get('left', phys_origin_x))
                    phys_origin_y = int(matched.get('top', phys_origin_y))
            except Exception:
                pass

            phys_left = phys_origin_x + int(round((nx - logical_origin_x) * dpr))
            phys_top = phys_origin_y + int(round((ny - logical_origin_y) * dpr))
            phys_w = int(round(nw * dpr))
            phys_h = int(round(nh * dpr))
        except Exception:
            # Fallback: scale by widget DPR
            dpr = float(self.devicePixelRatioF() if hasattr(self, 'devicePixelRatioF') else 1.0)
            phys_left = int(round(nx * dpr))
            phys_top = int(round(ny * dpr))
            phys_w = int(round(nw * dpr))
            phys_h = int(round(nh * dpr))

        # write overlay->capture mapping debug info
        try:
            import os, time
            dbgdir = os.path.join(os.path.dirname(__file__), 'logs')
            os.makedirs(dbgdir, exist_ok=True)
            dbgfile = os.path.join(dbgdir, 'capture_overlay_debug.txt')
            with open(dbgfile, 'a', encoding='utf-8') as f:
                f.write(f"time: {time.time()}\n")
                f.write(f"logical_sel: {(x, y, w, h)}\n")
                f.write(f"inset_sel: {(nx, ny, nw, nh)}\n")
                try:
                    sgeom = screen.geometry()
                    f.write(f"screen_geom: {sgeom.x()},{sgeom.y()},{sgeom.width()},{sgeom.height()}\n")
                except Exception:
                    f.write("screen_geom: <error>\n")
                f.write(f"dpr: {dpr}\n")
                try:
                    f.write(f"phys_origin: {phys_origin_x},{phys_origin_y}\n")
                    f.write(f"phys_rect: {(phys_left, phys_top, phys_w, phys_h)}\n")
                except Exception:
                    f.write("phys: <error>\n")
                f.write('\n')
        except Exception:
            pass

        # Clamp to virtual desktop physical bounds if mss available
        try:
            import mss as _mss
            v = _mss.mss().monitors[0]
            vleft = int(v.get('left', 0))
            vtop = int(v.get('top', 0))
            vright = vleft + int(v.get('width', 0))
            vbottom = vtop + int(v.get('height', 0))
            if phys_left < vleft:
                phys_left = vleft
            if phys_top < vtop:
                phys_top = vtop
            if phys_left + phys_w > vright:
                phys_left = max(vleft, vright - phys_w)
            if phys_top + phys_h > vbottom:
                phys_top = max(vtop, vbottom - phys_h)
        except Exception:
            pass

        return (phys_left, phys_top, phys_w, phys_h)
