#!/usr/bin/env python3
import os
import time
import csv
import json
import glob
import sys
import uuid
from pathlib import Path
import shutil

# Ensure repository root is on sys.path so top-level modules (e.g., utils)
# can be imported when this script is executed from the tests/ directory.
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
ffmpeg_path = shutil.which("ffmpeg")
gifsicle_path = shutil.which("gifsicle")
# Prefer repo/bin/ffmpeg over system or imageio; check repo-relative bin first
if not ffmpeg_path:
    try:
        file_path = Path(__file__).resolve()
        candidates = [file_path.parent.parent / "bin", file_path.parent / "bin"]
        for c in candidates:
            candidate = c / ("ffmpeg.exe" if os.name == "nt" else "ffmpeg")
            if candidate.exists():
                os.environ["SHRINK_FFMPEG_EXE"] = str(candidate)
                ffmpeg_path = str(candidate)
                print(f"Set SHRINK_FFMPEG_EXE to repo bin: {candidate}")
                break
    except Exception:
        pass

if not ffmpeg_path:
    print("Warning: ffmpeg not found; shrink will skip ffmpeg steps.")
if not gifsicle_path:
    # Try repo/bin gifsicle
    try:
        file_path = Path(__file__).resolve()
        for c in (file_path.parent.parent / "bin", file_path.parent / "bin"):
            candidate = c / ("gifsicle.exe" if os.name == "nt" else "gifsicle")
            if candidate.exists():
                os.environ["SHRINK_GIFSICLE_EXE"] = str(candidate)
                gifsicle_path = str(candidate)
                print(f"Set SHRINK_GIFSICLE_EXE to repo bin: {candidate}")
                break
    except Exception:
        pass
    if not gifsicle_path:
        print("Warning: gifsicle not found; gifsicle steps will be skipped.")

from utils import shrink_gif_to_target

OUT_DIR = Path("tmp_shrink_batch_out")
OUT_DIR.mkdir(exist_ok=True)
LOGS_DIR = Path("logs")
LOGS_DIR.mkdir(exist_ok=True)
REPORT = LOGS_DIR / "shrink_batch_report.csv"
METRICS_REPORT = LOGS_DIR / "shrink_batch_metrics_report.csv"
METRICS_LOG = LOGS_DIR / "shrink_metrics.jsonl"

TARGET_BYTES = int(os.environ.get("SHRINK_BATCH_TARGET_BYTES", str(2_000_000)))
RUN_ID = os.environ.get("SHRINK_METRICS_RUN_ID") or f"batch_{uuid.uuid4().hex[:10]}"
os.environ["SHRINK_METRICS_RUN_ID"] = RUN_ID
print(f"RUN_ID={RUN_ID}")

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

# parse metrics log for this run
metric_rows = []
if METRICS_LOG.exists():
    with open(METRICS_LOG, "r", encoding="utf-8") as mf:
        for line in mf:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except Exception:
                continue
            if obj.get("run_id") == RUN_ID:
                metric_rows.append(obj)

if metric_rows:
    with open(METRICS_REPORT, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "run_id",
                "input_gif",
                "target_bytes",
                "orig_size",
                "source_type",
                "cache_hit",
                "ffmpeg_variants",
                "ffmpeg_blacklist_skips",
                "ffmpeg_early_stop",
                "gifsicle_variants",
                "gifsicle_early_stop",
                "status",
                "result_path",
                "result_size",
                "duration_ms",
            ],
        )
        writer.writeheader()
        for r in metric_rows:
            writer.writerow({k: r.get(k, "") for k in writer.fieldnames})
    print(f"Metrics report written: {METRICS_REPORT}")

    def _avg(vals):
        vals = [float(v) for v in vals if v not in (None, "")]
        return (sum(vals) / len(vals)) if vals else 0.0

    avg_ms = _avg([r.get("duration_ms") for r in metric_rows])
    avg_ff = _avg([r.get("ffmpeg_variants") for r in metric_rows])
    avg_gs = _avg([r.get("gifsicle_variants") for r in metric_rows])
    cache_hits = {}
    for r in metric_rows:
        k = r.get("cache_hit") or "none"
        cache_hits[k] = cache_hits.get(k, 0) + 1
    print(
        "Metrics summary: "
        f"runs={len(metric_rows)} "
        f"avg_duration_ms={avg_ms:.1f} "
        f"avg_ffmpeg_variants={avg_ff:.2f} "
        f"avg_gifsicle_variants={avg_gs:.2f} "
        f"cache_hits={cache_hits}"
    )
else:
    print("No per-run metrics rows found in shrink_metrics.jsonl for this run_id.")
