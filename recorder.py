import logging
import threading
import time
from typing import Tuple, Optional

import mss
import numpy as np
import cv2


class ScreenRecorder:
    def __init__(self) -> None:
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._out_path: Optional[str] = None
        self._rect: Optional[Tuple[int, int, int, int]] = None
        self._fps = 10

    def _capture_loop(
        self, rect: Tuple[int, int, int, int], fps: int, out_path: str
    ) -> None:
        left, top, width, height = rect
        # write debug info about capture rect and monitors
        try:
            import os
            import json

            dbgdir = os.path.join(os.path.dirname(__file__), "logs")
            os.makedirs(dbgdir, exist_ok=True)
            dbgfile = os.path.join(dbgdir, "capture_debug.txt")
            with open(dbgfile, "a", encoding="utf-8") as f:
                f.write(f"time: {time.time()}\n")
                f.write(f"requested_rect: {rect}\n")
                try:
                    sct_tmp = mss.mss()
                    mons = sct_tmp.monitors
                    f.write(f"mss_monitors: {json.dumps(mons)}\n")
                except Exception as me:
                    f.write(f"mss_monitors_error: {me}\n")
                f.write("\n")
        except Exception:
            pass
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        writer = None
        sct = mss.mss()
        interval = 1.0 / float(max(1, fps))
        try:
            if width <= 0 or height <= 0:
                logging.error("Invalid capture dimensions: %s", rect)
                return
            writer = cv2.VideoWriter(out_path, fourcc, fps, (width, height))

            # performance diagnostics
            dbgdir = os.path.join(os.path.dirname(__file__), "logs")
            os.makedirs(dbgdir, exist_ok=True)
            perf_file = os.path.join(dbgdir, "capture_perf.txt")
            grab_times = []
            encode_times = []
            frame_count = 0
            last_report = time.perf_counter()

            while not self._stop_event.is_set():
                t0 = time.perf_counter()
                try:
                    tgrab = time.perf_counter()
                    img = sct.grab(
                        {"left": left, "top": top, "width": width, "height": height}
                    )
                    tgrab2 = time.perf_counter()
                    grab_times.append((tgrab2 - tgrab) * 1000.0)
                except Exception:
                    logging.exception("mss.grab failed in capture loop")
                    break

                # Use np.asarray to avoid an extra copy when possible
                arr = np.asarray(img)
                # convert BGRA to BGR if necessary
                if arr.ndim == 3 and arr.shape[2] == 4:
                    frame = cv2.cvtColor(arr, cv2.COLOR_BGRA2BGR)
                else:
                    frame = arr

                try:
                    tenc = time.perf_counter()
                    writer.write(frame)
                    tenc2 = time.perf_counter()
                    encode_times.append((tenc2 - tenc) * 1000.0)
                except Exception:
                    logging.exception("cv2 writer failed to write frame")
                    break

                # periodic diagnostic report (every ~1s)
                frame_count += 1
                now = time.perf_counter()
                if now - last_report >= 1.0:
                    try:
                        avg_grab = (
                            sum(grab_times) / len(grab_times) if grab_times else 0.0
                        )
                        avg_enc = (
                            sum(encode_times) / len(encode_times)
                            if encode_times
                            else 0.0
                        )
                        with open(perf_file, "a", encoding="utf-8") as pf:
                            pf.write(
                                f"{time.time()} frames={frame_count} "
                                f"avg_grab_ms={avg_grab:.2f} "
                                f"avg_enc_ms={avg_enc:.2f}\n"
                            )
                    except Exception:
                        pass
                    grab_times = []
                    encode_times = []
                    frame_count = 0
                    last_report = now

                # precise sleep using perf_counter to avoid drift
                elapsed = time.perf_counter() - t0
                to_sleep = interval - elapsed
                if to_sleep > 0:
                    time.sleep(to_sleep)
                else:
                    # If running behind, yield briefly to avoid a tight loop
                    time.sleep(0)
        except Exception:
            logging.exception("Unexpected exception in capture loop")
        finally:
            try:
                if writer is not None:
                    writer.release()
            except Exception:
                logging.exception("Failed to release video writer")
            finally:
                # Mark recorder as no longer running once the capture loop exits.
                self._thread = None

    def start(
        self, rect: Tuple[int, int, int, int], fps: int = 10, out_path: str = None
    ):
        if self.is_recording():
            return False
        self._stop_event.clear()
        self._rect = rect
        self._fps = fps
        self._out_path = out_path or "video/out.mp4"
        self._thread = threading.Thread(
            target=self._capture_loop, args=(rect, fps, self._out_path), daemon=True
        )
        self._thread.start()
        return True

    def is_recording(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def request_stop(self) -> None:
        self._stop_event.set()

    def wait_stopped(self, timeout: float = 5.0) -> bool:
        thread = self._thread
        if not thread:
            return True
        try:
            thread.join(timeout=timeout)
        except Exception:
            logging.exception("Exception while joining recorder thread")
            return False
        if thread.is_alive():
            logging.error("Recorder thread did not stop within %.1f seconds", timeout)
            return False
        self._thread = None
        return True

    def stop(self, timeout: float = 5.0):
        if not self._thread:
            return self._out_path, True
        self.request_stop()
        stopped_ok = self.wait_stopped(timeout=timeout)
        if not stopped_ok:
            logging.error("Recorder stop timed out; output may be incomplete")
        return self._out_path, stopped_ok
