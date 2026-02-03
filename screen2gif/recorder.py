import threading
import time
import queue
from typing import Tuple

import mss
import numpy as np
import cv2


class ScreenRecorder:
    def __init__(self):
        self._thread = None
        self._stop_event = threading.Event()
        self._out_path = None
        self._rect = None
        self._fps = 10

    def _capture_loop(self, rect: Tuple[int, int, int, int], fps: int, out_path: str):
        left, top, width, height = rect
        # write debug info about capture rect and monitors
        try:
            import os, time, json
            dbgdir = os.path.join(os.path.dirname(__file__), 'logs')
            os.makedirs(dbgdir, exist_ok=True)
            dbgfile = os.path.join(dbgdir, 'capture_debug.txt')
            with open(dbgfile, 'a', encoding='utf-8') as f:
                f.write(f"time: {time.time()}\n")
                f.write(f"requested_rect: {rect}\n")
                try:
                    sct_tmp = mss.mss()
                    mons = sct_tmp.monitors
                    f.write(f"mss_monitors: {json.dumps(mons)}\n")
                except Exception as me:
                    f.write(f"mss_monitors_error: {me}\n")
                f.write('\n')
        except Exception:
            pass
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        writer = cv2.VideoWriter(out_path, fourcc, fps, (width, height))
        sct = mss.mss()
        interval = 1.0 / fps
        try:
            while not self._stop_event.is_set():
                t0 = time.time()
                img = sct.grab({'left': left, 'top': top, 'width': width, 'height': height})
                arr = np.array(img)  # BGRA
                # convert BGRA to BGR
                if arr.shape[2] == 4:
                    arr = cv2.cvtColor(arr, cv2.COLOR_BGRA2BGR)
                writer.write(arr)
                dt = time.time() - t0
                to_sleep = interval - dt
                if to_sleep > 0:
                    time.sleep(to_sleep)
        finally:
            writer.release()

    def start(self, rect: Tuple[int, int, int, int], fps: int = 10, out_path: str = None):
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._rect = rect
        self._fps = fps
        self._out_path = out_path or 'video/out.mp4'
        self._thread = threading.Thread(target=self._capture_loop, args=(rect, fps, self._out_path), daemon=True)
        self._thread.start()

    def stop(self):
        if not self._thread:
            return None
        self._stop_event.set()
        self._thread.join()
        return self._out_path
