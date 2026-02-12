#!/usr/bin/env python3
import os
import time
import csv
import glob
import sys
from pathlib import Path
import shutil

# Ensure repository root is on sys.path so top-level modules (e.g., utils)
# can be imported when this script is executed from the tests/ directory.
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
ffmpeg_path = shutil.which("ffmpeg")
gifsicle_path = shutil.which("gifsicle")
# If system ffmpeg not present, try to use imageio_ffmpeg's bundled ffmpeg
# and set `SHRINK_FFMPEG_EXE` so shrink functions use it unambiguously.
if not ffmpeg_path:
    try:
        import imageio_ffmpeg
        bundled = imageio_ffmpeg.get_ffmpeg_exe()
        if bundled and Path(bundled).exists():
            os.environ["SHRINK_FFMPEG_EXE"] = str(bundled)
            print(f"Set SHRINK_FFMPEG_EXE to imageio_ffmpeg binary: {bundled}")
            ffmpeg_path = bundled
    except Exception:
        pass
if not ffmpeg_path:
    print("Warning: ffmpeg not found; shrink will skip ffmpeg steps.")
if not gifsicle_path:
    print("Warning: gifsicle not found; gifsicle steps will be skipped.")

from utils import shrink_gif_to_target

OUT_DIR = Path("tmp_shrink_batch_out")
OUT_DIR.mkdir(exist_ok=True)
LOGS_DIR = Path("logs")
LOGS_DIR.mkdir(exist_ok=True)
REPORT = LOGS_DIR / "shrink_batch_report.csv"

TARGET_BYTES = int(os.environ.get("SHRINK_BATCH_TARGET_BYTES", str(2_000_000)))

# find gif files
candidates = sorted(glob.glob("gif/*.gif") + glob.glob("pkg/minimal/gif/*.gif") + glob.glob("screen2gif/gif/*.gif"))
if not candidates:
    print("No GIFs found in gif/ or pkg/minimal/gif/ or screen2gif/gif/")
    raise SystemExit(1)

rows = []
for gif in candidates:
    name = Path(gif).stem
    out_sub = OUT_DIR / name
    out_sub.mkdir(parents=True, exist_ok=True)
    t0 = time.perf_counter()
    try:
        res = shrink_gif_to_target(gif, TARGET_BYTES, str(out_sub))
    except Exception as e:
        duration = time.perf_counter() - t0
        rows.append({"input": gif, "duration_s": f"{duration:.3f}", "output": "", "out_size": "", "success": "error", "error": str(e)})
        print(f"{gif}: ERROR {e}")
        continue
    duration = time.perf_counter() - t0
    if res and os.path.exists(res):
        size = os.path.getsize(res)
        success = "ok" if size <= TARGET_BYTES else "partial"
        rows.append({"input": gif, "duration_s": f"{duration:.3f}", "output": res, "out_size": str(size), "success": success, "error": ""})
        print(f"{gif}: {duration:.2f}s -> {res} ({size} bytes) [{success}]")
    else:
        rows.append({"input": gif, "duration_s": f"{duration:.3f}", "output": "", "out_size": "", "success": "none", "error": ""})
        print(f"{gif}: {duration:.2f}s -> no result")

# write CSV
with open(REPORT, "w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=["input", "duration_s", "output", "out_size", "success", "error"]) 
    writer.writeheader()
    for r in rows:
        writer.writerow(r)

print(f"Report written: {REPORT}")

# brief summary
total = len(rows)
ok = sum(1 for r in rows if r["success"] == "ok")
none = sum(1 for r in rows if r["success"] == "none")
err = sum(1 for r in rows if r["success"] == "error")
print(f"Processed {total} GIFs: ok={ok}, none={none}, error={err}")

# show top 5 slowest
sorted_rows = sorted(rows, key=lambda r: float(r["duration_s"]) if r["duration_s"] else 0, reverse=True)
print("Top 5 slowest:")
for r in sorted_rows[:5]:
    print(f"{r['input']} {r['duration_s']}s {r['success']} {r['out_size']}")
