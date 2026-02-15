"""Headless smoke test: record small region, convert to GIF,
and copy path to clipboard.
"""

import time
from utils import ensure_dirs, timestamped_filename
from recorder import ScreenRecorder
from converter import convert_mp4_to_gif
from clipboard_clean import copy_path_to_clipboard


def run_smoke():
    ensure_dirs()
    rec = ScreenRecorder()
    # record a small region at top-left for 2 seconds
    rect = (0, 0, 320, 240)
    mp4 = timestamped_filename("video", "mp4")
    gif = timestamped_filename("gif", "gif")
    print("SMOKE: starting recording ->", mp4)
    rec.start(rect, fps=10, out_path=mp4)
    time.sleep(2.2)
    print("SMOKE: stopping recording")
    mp4_path, stopped_ok = rec.stop()
    print("SMOKE: mp4_path=", mp4_path, "stopped_ok=", stopped_ok)
    if not stopped_ok or not mp4_path:
        print("SMOKE: recording failed")
        return 1
    print("SMOKE: converting to gif ->", gif)
    ok = convert_mp4_to_gif(mp4_path, gif, fps=10)
    print("SMOKE: convert ok=", ok)
    if ok:
        cp = copy_path_to_clipboard(gif)
        print("SMOKE: copied to clipboard:", cp, "gif=", gif)
        return 0
    print("SMOKE: convert failed")
    return 2


if __name__ == "__main__":
    raise SystemExit(run_smoke())
