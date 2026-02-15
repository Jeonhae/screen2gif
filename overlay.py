from PyQt5 import QtWidgets
from PyQt5 import QtCore
from PyQt5 import QtGui
import logging

from capture_utils import compute_physical_capture_region


class OverlayWindow(QtWidgets.QWidget):
    interaction = QtCore.pyqtSignal()

    def __init__(self):
        super().__init__()
        # Keep overlay frameless and make it stay on top of normal windows
        flags = (
            QtCore.Qt.FramelessWindowHint
            | QtCore.Qt.WindowStaysOnTopHint
            | QtCore.Qt.Window
        )
        self.setWindowFlags(flags)
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground)

        # Ensure we receive mouseMoveEvent even when no button is pressed
        # so hover over the pan handle can change the cursor.
        try:
            self.setMouseTracking(True)
        except Exception:
            pass

        self.selection_rect = None  # QRect or None
        self._dragging_handle = None  # index 0-7 for control handles, or None
        self._drag_offset = None
        self.handle_size = 8
        self.control_handles = []  # list of QRect for handles
        # Top-center pan handle (short line + small circle)
        self.pan_line_length = 30
        self.pan_circle_diameter = 20
        self.pan_handle_rect = None

        # For drawing new selection
        self._start_pos = None
        # True when the user is actively dragging to create/resize the selection
        self._is_dragging_selection = False
        # Minimum movement (pixels) before we treat a press+move as a drag
        self._drag_threshold = 20

        # Recording indicator (blinking)
        self.is_recording = False
        self._blink_visible = True
        self._blink_timer = QtCore.QTimer(self)
        self._blink_timer.setInterval(500)
        self._blink_timer.timeout.connect(self._toggle_blink)

    def _toggle_blink(self):
        self._blink_visible = not self._blink_visible
        self.update()

    def is_selection_visible(self):
        """Return True when the selection border and handles should be visible.

        Matches the same condition used in paintEvent for blinking.
        """
        try:
            return (not getattr(self, "is_recording", False)) or (
                getattr(self, "is_recording", False)
                and getattr(self, "_blink_visible", True)
            )
        except Exception:
            return True

    def is_controls_visible(self):
        """Return True when control handles and pan handle should be visible.

        Controls should be hidden during recording (to avoid blinking with the border).
        """
        try:
            return not getattr(self, "is_recording", False)
        except Exception:
            return True

    def _raise_toolbar(self):
        """Ensure the toolbar window stays on top by raising any top-level
        widget with the title 'Screen2GIF'."""
        # Avoid changing flags or repeatedly calling show()/activateWindow(),
        # which can cause a visible flash. Simply raise the toolbar window
        # so it stays above the overlay when needed.
        try:
            for w in QtWidgets.QApplication.topLevelWidgets():
                try:
                    if (
                        getattr(w, "objectName", None)
                        and w.objectName() == "Screen2GIFToolbar"
                    ) or hasattr(w, "start_btn"):
                        try:
                            w.raise_()
                        except Exception:
                            pass
                except Exception:
                    pass
        except Exception:
            pass

    def start_recording(self):
        self.is_recording = True
        self._blink_visible = True
        # Allow clicks to pass through so the user can interact with apps
        # while recording.
        try:
            self.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents, True)
        except Exception:
            pass
        self._blink_timer.start()
        self.update()
        # Ensure toolbar remains on top when recording state changes
        self._raise_toolbar()

    def stop_recording(self):
        self.is_recording = False
        self._blink_timer.stop()
        self._blink_visible = True
        try:
            self.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents, False)
        except Exception:
            pass
        self.update()
        # Ensure toolbar remains on top when recording stops
        self._raise_toolbar()

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)

        # Dim the screen only during selection. Keep it transparent while
        # recording. For visual-less mode set alpha to 0 so the overlay
        # is fully transparent but selection/controls logic remains.
        if not self.is_recording:
            overlay_color = QtGui.QColor(0, 0, 0, 0)  # alpha = 0 (fully transparent)
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

            # selection border (red dashed). Blink when recording
            pen = QtGui.QPen(QtGui.QColor(255, 0, 0))
            pen.setWidth(4)
            pen.setStyle(QtCore.Qt.DashLine)
            painter.setPen(pen)
            visible = (not self.is_recording) or (
                self.is_recording and self._blink_visible
            )
            # draw border according to blink state
            if visible:
                painter.drawRect(rectf)

            # controls are drawn only when controls_visible (i.e., not recording)
            try:
                controls_visible = self.is_controls_visible()
            except Exception:
                controls_visible = True

            if controls_visible:
                # compute handles and pan geometry first
                self.update_control_handles()

                # draw top-center pan handle first so it appears beneath control handles
                try:
                    if self.pan_handle_rect is not None:
                        # compute center top point relative to selection_rect
                        r = self.selection_rect
                        cx = (r.left() + r.right()) / 2.0
                        top_y = r.top()
                        line_len = self.pan_line_length
                        # line from (cx, top_y) to (cx, top_y - line_len)
                        pen_line = QtGui.QPen(QtGui.QColor(255, 0, 0))
                        pen_line.setWidth(2)
                        painter.setPen(pen_line)
                        painter.drawLine(
                            int(cx), int(top_y), int(cx), int(top_y - line_len)
                        )

                        # draw filled circle at end
                        circle_rect = QtCore.QRectF(self.pan_handle_rect)
                        brush = QtGui.QBrush(QtGui.QColor(255, 0, 0))
                        painter.setBrush(brush)
                        painter.setPen(QtGui.QPen(QtCore.Qt.NoPen))
                        painter.drawEllipse(circle_rect)
                except Exception:
                    pass

                # draw control handles on top of the pan handle
                brush = QtGui.QBrush(QtGui.QColor(255, 255, 255))
                pen2 = QtGui.QPen(QtGui.QColor(0, 0, 0))
                painter.setBrush(brush)
                painter.setPen(pen2)
                for h in self.control_handles:
                    painter.drawRect(QtCore.QRectF(h))
            else:
                # when controls are hidden (during recording), ensure no handles linger
                try:
                    self.control_handles = []
                except Exception:
                    pass
                try:
                    self.pan_handle_rect = None
                except Exception:
                    pass

    def mousePressEvent(self, event):
        if event.button() != QtCore.Qt.LeftButton:
            return
        pos = event.pos()

        # Only allow handle/pan interaction when selection is visible
        # (not in hidden blink frame)
        if self.is_selection_visible():
            # check if clicking a control handle
            for idx, h in enumerate(self.control_handles):
                if h.contains(pos):
                    self._dragging_handle = idx
                    self._drag_offset = pos
                    return

            # check pan handle (circle)
            try:
                if self.pan_handle_rect and self.pan_handle_rect.contains(pos):
                    self._dragging_pan_handle = True
                    self._pan_start_pos = pos
                    self._pan_start_rect = (
                        QtCore.QRect(self.selection_rect)
                        if self.selection_rect
                        else None
                    )
                    return
            except Exception:
                pass

        # Record press position but do NOT start drawing selection until
        # the user moves the mouse while holding the left button.
        self._start_pos = pos
        self._is_dragging_selection = False
        # Do not create selection_rect here (so single clicks don't redraw)

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

            newr = QtCore.QRect(
                QtCore.QPoint(min(x1, x2), min(y1, y2)),
                QtCore.QPoint(max(x1, x2), max(y1, y2)),
            )
            self.selection_rect = newr
            self.update()
            return

        # handle pan-handle dragging
        try:
            if (
                getattr(self, "_dragging_pan_handle", False)
                and self._pan_start_rect is not None
                and self._pan_start_pos is not None
            ):
                dx = pos.x() - self._pan_start_pos.x()
                dy = pos.y() - self._pan_start_pos.y()
                r = QtCore.QRect(self._pan_start_rect)
                new_x = r.x() + dx
                new_y = r.y() + dy
                # constrain to overlay bounds
                max_x = max(0, self.width() - r.width())
                max_y = max(0, self.height() - r.height())
                new_x = max(0, min(new_x, max_x))
                new_y = max(0, min(new_y, max_y))
                r.moveTo(new_x, new_y)
                self.selection_rect = r
                try:
                    self.update_control_handles()
                except Exception:
                    pass
                try:
                    self.interaction.emit()
                except Exception:
                    pass
                self.update()
                return
        except Exception:
            logging.exception("pan handle drag failed")

        # hover cursor change when over control handles or pan handle
        try:
            if self.is_selection_visible():
                # check control handles first and map to appropriate resize cursors
                handled = False
                for idx, h in enumerate(self.control_handles):
                    try:
                        if h.contains(pos):
                            cursor_map = {
                                0: QtCore.Qt.SizeFDiagCursor,  # NW
                                1: QtCore.Qt.SizeVerCursor,  # N
                                2: QtCore.Qt.SizeBDiagCursor,  # NE
                                3: QtCore.Qt.SizeHorCursor,  # E
                                4: QtCore.Qt.SizeFDiagCursor,  # SE
                                5: QtCore.Qt.SizeVerCursor,  # S
                                6: QtCore.Qt.SizeBDiagCursor,  # SW
                                7: QtCore.Qt.SizeHorCursor,  # W
                            }
                            try:
                                self.setCursor(
                                    cursor_map.get(idx, QtCore.Qt.ArrowCursor)
                                )
                            except Exception:
                                pass
                            handled = True
                            break
                    except Exception:
                        continue

                if not handled:
                    # then check pan handle
                    if self.pan_handle_rect and self.pan_handle_rect.contains(pos):
                        try:
                            self.setCursor(QtCore.Qt.SizeAllCursor)
                        except Exception:
                            pass
                    else:
                        try:
                            self.setCursor(QtCore.Qt.ArrowCursor)
                        except Exception:
                            pass
            else:
                # selection hidden: always arrow cursor
                try:
                    self.setCursor(QtCore.Qt.ArrowCursor)
                except Exception:
                    pass
        except Exception:
            pass

        # If a press was recorded, only begin selection if left button is held
        # and movement exceeds the threshold.
        if self._start_pos is not None:
            buttons = event.buttons()
            if buttons & QtCore.Qt.LeftButton:
                # compute squared distance to avoid sqrt
                dx = pos.x() - self._start_pos.x()
                dy = pos.y() - self._start_pos.y()
                if not self._is_dragging_selection:
                    if dx * dx + dy * dy >= self._drag_threshold * self._drag_threshold:
                        self._is_dragging_selection = True
                        # initialize selection rect
                        self.selection_rect = QtCore.QRect(
                            self._start_pos, pos
                        ).normalized()
                        try:
                            self.interaction.emit()
                        except Exception:
                            pass
                        self.update()
                else:
                    # already dragging: update selection
                    self.selection_rect = QtCore.QRect(
                        self._start_pos, pos
                    ).normalized()
                    try:
                        self.interaction.emit()
                    except Exception:
                        pass
                    self.update()
            else:
                # mouse moved without left button: cancel potential selection start
                self._start_pos = None
                self._is_dragging_selection = False

    def mouseReleaseEvent(self, event):
        if event.button() != QtCore.Qt.LeftButton:
            return
        # determine whether we were interacting with handles
        was_dragging_handle = self._dragging_handle is not None

        # end dragging or selection
        self._dragging_handle = None
        self._drag_offset = None

        # end pan-handle drag
        was_pan = getattr(self, "_dragging_pan_handle", False)
        self._dragging_pan_handle = False
        self._pan_start_pos = None
        self._pan_start_rect = None

        # If the user dragged, finalize the selection; if it was only a click,
        # preserve the existing selection rectangle unchanged.
        if self._is_dragging_selection:
            self._start_pos = None
            if self.selection_rect:
                self.selection_rect = self.selection_rect.normalized()
                self.update_control_handles()
        else:
            # Simple click: don't modify the existing selection.
            # Clear temporary state.
            self._start_pos = None

        # Decide whether to emit interaction: only when a drag or handle
        # operation occurred.
        should_emit = was_dragging_handle or self._is_dragging_selection or was_pan

        # Reset dragging flag
        self._is_dragging_selection = False

        if should_emit:
            try:
                self.interaction.emit()
            except Exception:
                pass

        # Only raise the toolbar when a meaningful interaction occurred
        # (dragging the selection or resizing via handles). Avoid raising on
        # simple clicks to prevent visual flicker.
        if should_emit:
            try:
                self._raise_toolbar()
            except Exception:
                pass

        self.update()

    def update_control_handles(self):
        self.control_handles = []
        # reset pan handle by default
        self.pan_handle_rect = None
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
        for px, py in points:
            self.control_handles.append(QtCore.QRect(px - s // 2, py - s // 2, s, s))

        # compute top-center pan handle rect (circle at end of short upward line)
        try:
            line_len = int(self.pan_line_length)
            d = int(self.pan_circle_diameter)
            top_y = r.top()
            cx_f = (r.left() + r.right()) / 2.0
            circle_cx = int(cx_f)
            circle_cy = int(top_y - line_len)
            self.pan_handle_rect = QtCore.QRect(
                circle_cx - d // 2, circle_cy - d // 2, d, d
            )
        except Exception:
            self.pan_handle_rect = None

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
        nx = x + padding
        ny = y + padding
        nw = max(1, w - 2 * padding)
        nh = max(1, h - 2 * padding)

        return compute_physical_capture_region(nx, ny, nw, nh, self)

    def is_recording_active(self):
        """Return True if overlay is currently in recording (blinking) state."""
        try:
            return bool(getattr(self, "is_recording", False))
        except Exception:
            return False
