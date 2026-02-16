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
        self._start_event = threading.Event()
        self._start_ok = False

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
            logging.exception("Failed to write capture debug header")
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        writer = None
        sct = None
        interval = 1.0 / float(max(1, fps))
        try:
            if width <= 0 or height <= 0:
                logging.error("Invalid capture dimensions: %s", rect)
                self._start_ok = False
                self._start_event.set()
                return
            sct = mss.mss()
            writer = cv2.VideoWriter(out_path, fourcc, fps, (width, height))
            if not writer.isOpened():
                logging.error("Failed to open VideoWriter for: %s", out_path)
                self._start_ok = False
                self._start_event.set()
                return
            self._start_ok = True
            self._start_event.set()

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
                        logging.debug(
                            "Failed to write capture performance report",
                            exc_info=True,
                        )
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
            if not self._start_event.is_set():
                self._start_ok = False
                self._start_event.set()
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
        self,
        rect: Tuple[int, int, int, int],
        fps: int = 10,
        out_path: str = None,
        startup_timeout: float = 3.0,
    ):
        if self.is_recording():
            return False
        self._stop_event.clear()
        self._rect = rect
        self._fps = fps
        self._out_path = out_path or "video/out.mp4"
        self._start_ok = False
        self._start_event.clear()
        self._thread = threading.Thread(
            target=self._capture_loop, args=(rect, fps, self._out_path), daemon=True
        )
        self._thread.start()
        timeout = max(0.0, float(startup_timeout))
        deadline = time.perf_counter() + timeout
        while True:
            now = time.perf_counter()
            remaining = max(0.0, deadline - now)
            if self._start_event.wait(timeout=min(0.2, remaining)):
                return self._start_ok

            # If the thread exited before signaling startup, treat as failure.
            if not (self._thread and self._thread.is_alive()):
                logging.error("Recorder thread exited before initialization finished")
                return False

            if remaining <= 0.0:
                logging.error(
                    "Recorder start timed out before capture loop initialized "
                    "(timeout=%.2fs)",
                    timeout,
                )
                return False

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
        # If not currently recording, return immediately without exposing
        # any previously used output path (avoid returning stale paths).
        if not self.is_recording():
            return None, False
        self.request_stop()
        stopped_ok = self.wait_stopped(timeout=timeout)
        if not stopped_ok:
            logging.error("Recorder stop timed out; output may be incomplete")
        out_path = self._out_path
        if stopped_ok:
            # Clear stored output path once the recorder stopped cleanly to
            # avoid later accidental reuse.
            self._out_path = None
        else:
            # On failure, don't leak the old path; return None when stop not ok.
            out_path = None
        return out_path, stopped_ok
