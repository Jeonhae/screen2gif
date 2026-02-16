import os
import time
import json
import shutil
import subprocess
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Tuple
import logging

# Do not use imageio_ffmpeg fallback - prefer repo/bin/ffmpeg or system ffmpeg.


def get_subprocess_no_window_kwargs() -> dict:
    """Return subprocess kwargs to suppress console windows on Windows."""
    # This is used for external tool invocations (ffmpeg, gifsicle)
    # to ensure they run silently without popping up console windows
    # on Windows. Callers should merge these kwargs into their
    # subprocess.run invocations or use `run_hidden()`.
    if os.name != "nt":
        return {}

    kwargs = {}
    try:
        kwargs["creationflags"] = int(subprocess.CREATE_NO_WINDOW)
    except Exception:
        pass

    try:
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = 0
        kwargs["startupinfo"] = startupinfo
    except Exception:
        pass

    return kwargs


def run_hidden(cmd, **kwargs):
    """Run subprocess with hidden-window flags on Windows."""
    merged = dict(kwargs)
    hidden = get_subprocess_no_window_kwargs()

    hidden_creationflags = hidden.get("creationflags")
    if hidden_creationflags is not None:
        existing = int(merged.get("creationflags", 0))
        merged["creationflags"] = existing | int(hidden_creationflags)

    if "startupinfo" in hidden and "startupinfo" not in merged:
        merged["startupinfo"] = hidden["startupinfo"]

    return subprocess.run(cmd, **merged)


def ensure_dirs(base_dir=None):
    base = base_dir or os.path.dirname(__file__)
    for d in ("video", "gif", "logs"):
        p = os.path.join(base, d)
        os.makedirs(p, exist_ok=True)


def resolve_ffmpeg_exe() -> Optional[str]:
    """Resolve ffmpeg executable path using repo/local preferences.

    Order of preference:
    1. Environment variable `SHRINK_FFMPEG_EXE`
    2. Repo-local `bin/ffmpeg` (preferred)
    3. System `ffmpeg` on PATH
    """
    ffmpeg_exe = os.environ.get("SHRINK_FFMPEG_EXE")
    if ffmpeg_exe and not os.path.exists(ffmpeg_exe):
        ffmpeg_exe = None

    if not ffmpeg_exe:
        try:
            file_path = Path(__file__).resolve()
            candidates = [
                file_path.parent / "bin",
                file_path.parent.parent / "bin",
                file_path.parent.parent.parent / "bin",
            ]
            for c in candidates:
                candidate = c / ("ffmpeg.exe" if os.name == "nt" else "ffmpeg")
                if candidate.exists():
                    ffmpeg_exe = str(candidate)
                    break
        except Exception:
            pass

    if not ffmpeg_exe:
        ffmpeg_exe = shutil.which("ffmpeg")

    return ffmpeg_exe


def timestamped_filename(folder: str, ext: str) -> str:
    base = os.path.dirname(__file__)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return os.path.join(base, folder, f"{ts}.{ext}")


def clear_video_folder(
    base_dir: Optional[str] = None,
) -> Tuple[List[str], List[Tuple[str, str]]]:
    """Remove all files and subdirectories inside the project's `video` folder.

    - Keeps the `video` folder itself.
    - Returns a tuple `(removed, errors)` where `removed` is a list of
      successfully removed paths and `errors` is a list of `(path, error_msg)`.

    Args:
        base_dir: Optional base directory. Defaults to the package directory.
    """
    base = base_dir or os.path.dirname(__file__)
    target = os.path.join(base, "video")
    removed: List[str] = []
    errors: List[Tuple[str, str]] = []

    if not os.path.exists(target):
        return removed, errors

    for name in os.listdir(target):
        path = os.path.join(target, name)
        try:
            if os.path.islink(path) or os.path.isfile(path):
                os.remove(path)
                removed.append(path)
            elif os.path.isdir(path):
                shutil.rmtree(path)
                removed.append(path)
        except Exception as e:
            errors.append((path, str(e)))

    return removed, errors


def clear_gif_folder(
    base_dir: Optional[str] = None,
) -> Tuple[List[str], List[Tuple[str, str]]]:
    """Remove all files and subdirectories inside the project's `gif` folder.

    - Keeps the `gif` folder itself.
    - Returns a tuple `(removed, errors)` where `removed` is a list of
      successfully removed paths and `errors` is a list of `(path, error_msg)`.
    """
    base = base_dir or os.path.dirname(__file__)
    target = os.path.join(base, "gif")
    removed: List[str] = []
    errors: List[Tuple[str, str]] = []

    if not os.path.exists(target):
        return removed, errors

    for name in os.listdir(target):
        path = os.path.join(target, name)
        try:
            if os.path.islink(path) or os.path.isfile(path):
                os.remove(path)
                removed.append(path)
            elif os.path.isdir(path):
                shutil.rmtree(path)
                removed.append(path)
        except Exception as e:
            errors.append((path, str(e)))

    return removed, errors


def shrink_gif_to_target(
    gif_path: str,
    target_bytes: int,
    out_dir: str,
    source_mp4_path: Optional[str] = None,
) -> Optional[str]:
    """Reduce `gif_path` to be <= `target_bytes` and place result in `out_dir`.

    Returns path to produced GIF in `out_dir` on success, otherwise None.
    """
    run_started = time.perf_counter()
    metrics = {
        "run_id": os.environ.get("SHRINK_METRICS_RUN_ID", ""),
        "input_gif": os.path.abspath(gif_path),
        "target_bytes": int(target_bytes),
        "orig_size": None,
        "source_type": "gif",
        "cache_hit": "",
        "ffmpeg_variants": 0,
        "ffmpeg_blacklist_skips": 0,
        "ffmpeg_early_stop": False,
        "gifsicle_variants": 0,
        "gifsicle_early_stop": False,
        "status": "unknown",
        "result_path": "",
        "result_size": None,
        "time_budget_ms": None,
        "time_budget_hit": False,
    }

    def _emit_metrics(status: str, result_path: Optional[str] = None):
        try:
            metrics["status"] = status
            if result_path:
                metrics["result_path"] = os.path.abspath(result_path)
                try:
                    metrics["result_size"] = os.path.getsize(result_path)
                except Exception:
                    metrics["result_size"] = None
            metrics["duration_ms"] = round(
                (time.perf_counter() - run_started) * 1000.0,
                2,
            )
            log_dir = os.path.join(os.path.dirname(__file__), "logs")
            os.makedirs(log_dir, exist_ok=True)
            log_path = os.path.join(log_dir, "shrink_metrics.jsonl")
            with open(log_path, "a", encoding="utf-8") as mf:
                mf.write(json.dumps(metrics, ensure_ascii=False) + "\n")
        except Exception:
            pass

    if not os.path.exists(gif_path):
        _emit_metrics("input_missing")
        return None

    os.makedirs(out_dir, exist_ok=True)

    try:
        orig_size = os.path.getsize(gif_path)
    except Exception:
        _emit_metrics("input_stat_failed")
        return None
    metrics["orig_size"] = int(orig_size)

    if orig_size <= target_bytes:
        dst = os.path.join(out_dir, os.path.basename(gif_path))
        shutil.copy2(gif_path, dst)
        _emit_metrics("already_small", dst)
        return dst

    # debug info
    logging.debug(f"[shrink] orig_size={orig_size} target_bytes={target_bytes}")
    ffmpeg_input = (
        source_mp4_path
        if source_mp4_path and os.path.exists(source_mp4_path)
        else gif_path
    )
    metrics["source_type"] = "mp4" if ffmpeg_input != gif_path else "gif"

    ffmpeg_exe = resolve_ffmpeg_exe()
    # Prefer repo/bin/gifsicle, then env var SHRINK_GIFSICLE_EXE, then system gifsicle
    gifsicle_exe = os.environ.get("SHRINK_GIFSICLE_EXE")
    if gifsicle_exe and not os.path.exists(gifsicle_exe):
        gifsicle_exe = None
    if not gifsicle_exe:
        try:
            file_path = Path(__file__).resolve()
            candidates = [
                file_path.parent / "bin",
                file_path.parent.parent / "bin",
                file_path.parent.parent.parent / "bin",
            ]
            for c in candidates:
                candidate = c / ("gifsicle.exe" if os.name == "nt" else "gifsicle")
                if candidate.exists():
                    gifsicle_exe = str(candidate)
                    break
        except Exception:
            pass
    if not gifsicle_exe:
        gifsicle_exe = shutil.which("gifsicle")
    logging.debug(f"[shrink] ffmpeg_exe={ffmpeg_exe} gifsicle_exe={gifsicle_exe}")

    tmpdir = tempfile.mkdtemp(prefix="shrink_gif_")
    best_candidate: Optional[str] = None
    best_size: Optional[int] = None
    best_fit_candidate: Optional[str] = None
    best_fit_size: Optional[int] = None
    best_fit_rank: Optional[Tuple[int, int, int, int]] = None
    try:
        time_budget_ms = int(os.environ.get("SHRINK_TIME_BUDGET_MS", "12000"))
    except Exception:
        time_budget_ms = 12000
    time_budget_ms = max(0, time_budget_ms)
    metrics["time_budget_ms"] = int(time_budget_ms)
    budget_deadline = (
        time.perf_counter() + (time_budget_ms / 1000.0)
        if time_budget_ms > 0
        else None
    )

    def _time_budget_exceeded() -> bool:
        if budget_deadline is None:
            return False
        if time.perf_counter() >= budget_deadline:
            metrics["time_budget_hit"] = True
            return True
        return False

    def _consider(path: str) -> bool:
        nonlocal best_candidate, best_size
        try:
            s = os.path.getsize(path)
        except Exception:
            return False
        if s <= target_bytes:
            best_candidate = path
            best_size = s
            return True
        if best_size is None or s < best_size:
            best_candidate = path
            best_size = s
        return False

    def _consider_fit(path: str, rank: Tuple[int, int, int, int]) -> bool:
        nonlocal best_fit_candidate, best_fit_size, best_fit_rank
        try:
            s = os.path.getsize(path)
        except Exception:
            return False
        _consider(path)
        if s > target_bytes:
            return False
        if (
            best_fit_candidate is None
            or best_fit_rank is None
            or rank > best_fit_rank
            or (rank == best_fit_rank and (best_fit_size is None or s < best_fit_size))
        ):
            best_fit_candidate = path
            best_fit_size = s
            best_fit_rank = rank
        return True

    try:
        # ffmpeg palette attempts
        def _run_cmd_timed(cmd, **kwargs):
            t0 = time.perf_counter()
            try:
                if _time_budget_exceeded():
                    raise TimeoutError("shrink time budget exceeded")
                run_hidden(cmd, **kwargs)
            finally:
                t1 = time.perf_counter()
                try:
                    dbgdir = os.path.join(os.path.dirname(__file__), "logs")
                    os.makedirs(dbgdir, exist_ok=True)
                    with open(
                        os.path.join(dbgdir, "shrink_perf.txt"),
                        "a",
                        encoding="utf-8",
                    ) as pf:
                        pf.write(
                            f"{time.time()} cmd={' '.join(cmd)} "
                            f"duration_ms={(t1 - t0) * 1000:.1f}\n"
                        )
                except Exception:
                    pass

        if ffmpeg_exe:
            min_width = 320
            produced = {}
            produced_events = {}
            palette_cache = {}
            state_lock = threading.Lock()
            palette_lock = threading.Lock()
            try:
                max_ffmpeg_variants = int(
                    os.environ.get("SHRINK_MAX_FFMPEG_VARIANTS", "8")
                )
            except Exception:
                max_ffmpeg_variants = 8
            max_ffmpeg_variants = max(1, max_ffmpeg_variants)
            ffmpeg_variants_tried = [0]
            try:
                ffmpeg_parallel_workers = int(
                    os.environ.get("SHRINK_FFMPEG_PARALLEL_WORKERS", "2")
                )
            except Exception:
                ffmpeg_parallel_workers = 2
            ffmpeg_parallel_workers = max(1, min(3, ffmpeg_parallel_workers))
            try:
                width_prune_ratio = float(
                    os.environ.get("SHRINK_WIDTH_PRUNE_RATIO", "1.8")
                )
            except Exception:
                width_prune_ratio = 1.8
            width_prune_ratio = max(1.0, width_prune_ratio)
            try:
                early_stop_min_improve = float(
                    os.environ.get("SHRINK_EARLY_STOP_MIN_IMPROVE", "0.02")
                )
            except Exception:
                early_stop_min_improve = 0.02
            try:
                early_stop_streak_limit = int(
                    os.environ.get("SHRINK_EARLY_STOP_STREAK", "2")
                )
            except Exception:
                early_stop_streak_limit = 2
            early_stop_min_improve = max(0.0, early_stop_min_improve)
            early_stop_streak_limit = max(1, early_stop_streak_limit)
            early_stop_triggered = [False]
            last_oversize = [None]
            low_improve_streak = [0]

            cache_path = os.path.join(
                os.path.dirname(__file__), "logs", "shrink_param_cache.json"
            )
            cache_lock_path = cache_path + ".lock"
            cache_data = {}
            cache_io_lock = threading.Lock()
            try:
                blacklist_ttl_sec = int(
                    os.environ.get("SHRINK_BLACKLIST_TTL_SEC", "900")
                )
            except Exception:
                blacklist_ttl_sec = 900
            blacklist_ttl_sec = max(60, blacklist_ttl_sec)

            # Overall time budget for this shrink run (milliseconds).
            # If exceeded, operations should abort early to respect latency.
            try:
                time_budget_ms = int(os.environ.get("SHRINK_TIME_BUDGET_MS", "15000"))
            except Exception:
                time_budget_ms = 15000
            time_budget_ms = max(1000, time_budget_ms)
            metrics["time_budget_ms"] = int(time_budget_ms)

            # Adjustable neighbor cache score threshold (higher -> more aggressive hits)
            try:
                neighbor_score_threshold = float(
                    os.environ.get("SHRINK_NEIGHBOR_SCORE_THRESHOLD", "0.4")
                )
            except Exception:
                neighbor_score_threshold = 0.4
            neighbor_score_threshold = max(0.0, min(1.0, float(neighbor_score_threshold)))
            metrics["neighbor_score_threshold"] = neighbor_score_threshold

            def _time_exceeded():
                try:
                    elapsed_ms = (time.perf_counter() - run_started) * 1000.0
                    if elapsed_ms > float(time_budget_ms):
                        metrics["time_budget_exceeded"] = True
                        return True
                except Exception:
                    pass
                return False

            def _run_palette(width, fps):
                scale_expr = (
                    f"scale={width}:-1:flags=lanczos"
                    if width
                    else "scale=iw:ih:flags=lanczos"
                )
                tag = f'{fps}_{width or "orig"}'
                palette_key = f'{width or "orig"}_{int(fps)}'
                with palette_lock:
                    palette = palette_cache.get(palette_key)
                    if not palette:
                        palette = os.path.join(tmpdir, f"palette_{palette_key}.png")
                        _run_cmd_timed(
                            [
                                ffmpeg_exe,
                                "-y",
                                "-i",
                                ffmpeg_input,
                                "-vf",
                                ("fps=" + str(fps) + "," + scale_expr + ",palettegen"),
                                palette,
                            ],
                            check=True,
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL,
                        )
                        palette_cache[palette_key] = palette
                out_gif = os.path.join(tmpdir, f"ff_{tag}.gif")
                _run_cmd_timed(
                    [
                        ffmpeg_exe,
                        "-y",
                        "-i",
                        ffmpeg_input,
                        "-i",
                        palette,
                        "-lavfi",
                        (
                            "fps=" + str(fps) + "," + scale_expr + "[x];"
                            "[x][1:v]paletteuse=dither=floyd_steinberg"
                        ),
                        out_gif,
                    ],
                    check=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                return out_gif

            def _fits_target(path):
                try:
                    size = os.path.getsize(path)
                except Exception:
                    return False
                _consider(path)
                return size <= target_bytes

            def _update_early_stop(size: Optional[int]):
                if size is None or size <= target_bytes:
                    return
                prev = last_oversize[0]
                if prev is not None and prev > 0 and size < prev:
                    improve = float(prev - size) / float(prev)
                    if improve < early_stop_min_improve:
                        low_improve_streak[0] += 1
                    else:
                        low_improve_streak[0] = 0
                else:
                    low_improve_streak[0] = 0
                last_oversize[0] = size
                if low_improve_streak[0] >= early_stop_streak_limit:
                    early_stop_triggered[0] = True
                    metrics["ffmpeg_early_stop"] = True
                    logging.debug(
                        "[shrink] early-stop triggered: low improvement streak reached"
                    )

            def _acquire_cache_file_lock(timeout_sec: float = 2.0):
                deadline = time.perf_counter() + max(0.1, timeout_sec)
                while True:
                    try:
                        fd = os.open(
                            cache_lock_path,
                            os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                        )
                        try:
                            os.write(fd, str(os.getpid()).encode("ascii", "ignore"))
                        except Exception:
                            pass
                        return fd
                    except FileExistsError:
                        if time.perf_counter() >= deadline:
                            return None
                        time.sleep(0.05)
                    except Exception:
                        return None

            def _release_cache_file_lock(fd) -> None:
                try:
                    os.close(fd)
                except Exception:
                    pass
                try:
                    if os.path.exists(cache_lock_path):
                        os.remove(cache_lock_path)
                except Exception:
                    pass

            # Attempt an initial, lock-protected read of the cache to avoid
            # races with concurrent writers from other processes. If acquiring
            # the file lock fails, fall back to a best-effort read without
            # the lock.
            try:
                lock_fd = _acquire_cache_file_lock(timeout_sec=0.5)
                if lock_fd is not None:
                    try:
                        with open(cache_path, "r", encoding="utf-8") as cf:
                            obj = json.load(cf)
                            if isinstance(obj, dict):
                                cache_data = obj
                    except Exception:
                        cache_data = {}
                    finally:
                        _release_cache_file_lock(lock_fd)
                else:
                    try:
                        with open(cache_path, "r", encoding="utf-8") as cf:
                            obj = json.load(cf)
                            if isinstance(obj, dict):
                                cache_data = obj
                    except Exception:
                        cache_data = {}
            except Exception:
                cache_data = {}

            def _persist_cache_locked():
                lock_fd = _acquire_cache_file_lock()
                if lock_fd is None:
                    return
                tmp_path = (
                    f"{cache_path}.tmp.{os.getpid()}."
                    f"{threading.get_ident()}.{int(time.time() * 1000)}"
                )
                try:
                    with open(tmp_path, "w", encoding="utf-8") as cf:
                        json.dump(cache_data, cf, ensure_ascii=False)
                    os.replace(tmp_path, cache_path)
                except Exception:
                    pass
                finally:
                    try:
                        if os.path.exists(tmp_path):
                            os.remove(tmp_path)
                    except Exception:
                        pass
                    _release_cache_file_lock(lock_fd)

            def _persist_cache():
                with cache_io_lock:
                    _persist_cache_locked()

            def _blacklist_key(width, fps):
                return f"{'orig' if width is None else int(width)}:{int(fps)}"

            def _blacklist_prune(now_ts: int):
                bm = cache_data.get("__ffmpeg_blacklist")
                if not isinstance(bm, dict):
                    cache_data["__ffmpeg_blacklist"] = {}
                    return
                expired = []
                for k, v in bm.items():
                    try:
                        ts = int(v)
                    except Exception:
                        expired.append(k)
                        continue
                    if now_ts - ts >= blacklist_ttl_sec:
                        expired.append(k)
                for k in expired:
                    bm.pop(k, None)

            def _blacklist_is_active(width, fps) -> bool:
                now_ts = int(time.time())
                with cache_io_lock:
                    _blacklist_prune(now_ts)
                    bm = cache_data.get("__ffmpeg_blacklist")
                    if not isinstance(bm, dict):
                        return False
                    ts = bm.get(_blacklist_key(width, fps))
                    if ts is None:
                        return False
                    try:
                        return now_ts - int(ts) < blacklist_ttl_sec
                    except Exception:
                        return False

            def _blacklist_mark_failure(width, fps):
                now_ts = int(time.time())
                with cache_io_lock:
                    _blacklist_prune(now_ts)
                    bm = cache_data.get("__ffmpeg_blacklist")
                    if not isinstance(bm, dict):
                        bm = {}
                        cache_data["__ffmpeg_blacklist"] = bm
                    bm[_blacklist_key(width, fps)] = now_ts
                    _persist_cache_locked()

            def _blacklist_mark_success(width, fps):
                with cache_io_lock:
                    bm = cache_data.get("__ffmpeg_blacklist")
                    if isinstance(bm, dict):
                        bm.pop(_blacklist_key(width, fps), None)
                    _persist_cache_locked()

            def _cache_set(cache_key: str, width, fps, alias_keys=None):
                try:
                    with cache_io_lock:
                        entry = {
                            "width": ("orig" if width is None else int(width)),
                            "fps": int(fps),
                            "ts": int(time.time()),
                        }
                        cache_data[cache_key] = entry
                        if alias_keys:
                            for ak in alias_keys:
                                if ak:
                                    cache_data[str(ak)] = dict(entry)

                        recent = cache_data.get("__recent_success")
                        if not isinstance(recent, list):
                            recent = []
                        recent.insert(
                            0,
                            {
                                "source": source_tag,
                                "width_now": int(hi_width),
                                "target_now": int(target_bytes),
                                "bucket_now": int(size_bucket_now),
                                "width": ("orig" if width is None else int(width)),
                                "fps": int(fps),
                                "ts": int(time.time()),
                            },
                        )
                        cache_data["__recent_success"] = recent[:20]
                        bm = cache_data.get("__ffmpeg_blacklist")
                        if isinstance(bm, dict):
                            bm.pop(_blacklist_key(width, fps), None)
                        _persist_cache_locked()
                except Exception:
                    pass

            def _normalize_cached_width(v):
                if v == "orig":
                    return None
                return int(v)

            def _try_cached_entry(cache_entry, cache_key_for_write: str):
                if not isinstance(cache_entry, dict):
                    return None
                try:
                    c_width = _normalize_cached_width(cache_entry.get("width"))
                    c_fps = int(cache_entry.get("fps"))
                    cached_path = _produce(c_width, c_fps)
                    if cached_path and _fits_target(cached_path):
                        _cache_set(cache_key_for_write, c_width, c_fps)
                        return cached_path
                except Exception:
                    return None
                return None

            def _parse_cache_key_meta(k: str):
                # Format: "{source}_w{width}_t{target}_b{bucket}"
                try:
                    p = str(k).split("_")
                    if len(p) != 4:
                        return None
                    src = p[0]
                    w = int(p[1][1:])
                    t = int(p[2][1:])
                    b = int(p[3][1:])
                    return src, w, t, b
                except Exception:
                    return None

            def _find_neighbor_cache_entry(
                src_tag: str, width_now: int, target_now: int, bucket_now: int
            ):
                best_key = None
                best_entry = None
                best_score = None
                denom_w = max(1.0, float(width_now))
                denom_t = max(1.0, float(target_now))
                denom_b = max(1.0, float(bucket_now if bucket_now > 0 else 1))
                with cache_io_lock:
                    cache_items = list(cache_data.items())
                for k, entry in cache_items:
                    meta = _parse_cache_key_meta(k)
                    if not meta:
                        continue
                    src, w, t, b = meta
                    if src != src_tag:
                        continue
                    dw = abs(float(w - width_now)) / denom_w
                    dt = abs(float(t - target_now)) / denom_t
                    db = abs(float(b - bucket_now)) / denom_b
                    score = (0.65 * dw) + (0.25 * dt) + (0.10 * db)
                    if best_score is None or score < best_score:
                        best_score = score
                        best_key = k
                        best_entry = entry
                if best_entry is None:
                    return None, None
                # Keep neighbor match reasonably close. Threshold is configurable
                # to allow more aggressive cache hits when desired.
                try:
                    thresh = float(neighbor_score_threshold)
                except Exception:
                    thresh = 0.4
                if best_score is not None and best_score <= thresh:
                    return best_key, best_entry
                return None, None

            def _find_recent_cache_entries(
                src_tag: str, width_now: int, target_now: int, bucket_now: int
            ):
                with cache_io_lock:
                    recent_obj = cache_data.get("__recent_success")
                    recent = list(recent_obj) if isinstance(recent_obj, list) else []
                if not isinstance(recent, list):
                    return []
                denom_w = max(1.0, float(width_now))
                denom_t = max(1.0, float(target_now))
                denom_b = max(1.0, float(bucket_now if bucket_now > 0 else 1))
                scored = []
                for item in recent:
                    if not isinstance(item, dict):
                        continue
                    if item.get("source") != src_tag:
                        continue
                    try:
                        iw = int(item.get("width_now", width_now))
                        it = int(item.get("target_now", target_now))
                        ib = int(item.get("bucket_now", bucket_now))
                    except Exception:
                        continue
                    dw = abs(float(iw - width_now)) / denom_w
                    dt = abs(float(it - target_now)) / denom_t
                    db = abs(float(ib - bucket_now)) / denom_b
                    score = (0.60 * dw) + (0.25 * dt) + (0.15 * db)
                    if score <= 0.55:
                        scored.append((score, item))
                scored.sort(key=lambda x: x[0])
                return [x[1] for x in scored[:3]]

            def _preferred_fps_from_recent(
                src_tag: str, width_now: int, target_now: int, bucket_now: int
            ) -> int:
                items = _find_recent_cache_entries(
                    src_tag, width_now, target_now, bucket_now
                )
                if not items:
                    return 10
                best_fps = None
                for it in items:
                    try:
                        fps = int(it.get("fps", 10))
                    except Exception:
                        continue
                    if best_fps is None:
                        best_fps = fps
                    else:
                        best_fps = int(round((best_fps + fps) / 2.0))
                if best_fps is None:
                    return 10
                return max(5, min(15, int(best_fps)))

            def _try_param_candidates(
                candidates,
                cache_hit_label: str,
                cache_key_for_write: str,
                alias_keys=None,
            ):
                seen = set()
                for width, fps in candidates:
                    if _time_budget_exceeded():
                        break
                    try:
                        norm_width = None if width in (None, "orig") else int(width)
                        norm_fps = max(5, min(15, int(fps)))
                    except Exception:
                        continue
                    key = (norm_width, norm_fps)
                    if key in seen:
                        continue
                    seen.add(key)
                    p = _produce(norm_width, norm_fps)
                    if not p:
                        continue
                    if _fits_target(p):
                        _cache_set(
                            cache_key_for_write,
                            norm_width,
                            norm_fps,
                            alias_keys=alias_keys,
                        )
                        metrics["cache_hit"] = cache_hit_label
                        return p
                return None

            def _produce(width, fps):
                key = (width, fps)
                while True:
                    run_self = False
                    wait_event = None
                    with state_lock:
                        if key in produced:
                            val = produced[key]
                            if val != "__RUNNING__":
                                return val
                            wait_event = produced_events.get(key)
                        else:
                            if _time_budget_exceeded():
                                produced[key] = None
                                return None
                            if early_stop_triggered[0] or (
                                ffmpeg_variants_tried[0] >= max_ffmpeg_variants
                            ):
                                produced[key] = None
                                return None
                            if _blacklist_is_active(width, fps):
                                metrics["ffmpeg_blacklist_skips"] += 1
                                produced[key] = None
                                return None
                            ffmpeg_variants_tried[0] += 1
                            metrics["ffmpeg_variants"] = ffmpeg_variants_tried[0]
                            produced[key] = "__RUNNING__"
                            wait_event = threading.Event()
                            produced_events[key] = wait_event
                            run_self = True
                    if not run_self:
                        if wait_event is not None:
                            wait_event.wait()
                        continue
                    result = None
                    try:
                        result = _run_palette(width, fps)
                        _blacklist_mark_success(width, fps)
                        try:
                            s = os.path.getsize(result) if result else None
                        except Exception:
                            s = None
                        with state_lock:
                            _update_early_stop(s)
                    except Exception:
                        result = None
                        _blacklist_mark_failure(width, fps)
                    finally:
                        with state_lock:
                            produced[key] = result
                            ev = produced_events.pop(key, None)
                            if ev is not None:
                                ev.set()
                    return result

            def _path_size(path):
                if not path:
                    return None
                try:
                    return os.path.getsize(path)
                except Exception:
                    return None

            def _eval_fps_candidates(width, fps_values):
                uniq = []
                seen = set()
                for fps in fps_values:
                    if fps in seen:
                        continue
                    seen.add(fps)
                    uniq.append(fps)
                results = {}
                if ffmpeg_parallel_workers <= 1 or len(uniq) <= 1:
                    for fps in uniq:
                        if _time_budget_exceeded():
                            break
                        results[fps] = _produce(width, fps)
                    return results
                with ThreadPoolExecutor(
                    max_workers=min(ffmpeg_parallel_workers, len(uniq))
                ) as ex:
                    fut_map = {ex.submit(_produce, width, fps): fps for fps in uniq}
                    for fut in as_completed(fut_map):
                        fps = fut_map[fut]
                        try:
                            results[fps] = fut.result()
                        except Exception:
                            results[fps] = None
                return results

            def _best_fps_path_for_width(width):
                if _time_budget_exceeded():
                    return None
                high_fps = 15
                low_fps = 5
                w_now = hi_width if width is None else int(width)
                pref_fps = _preferred_fps_from_recent(
                    source_tag, w_now, int(target_bytes), size_bucket_now
                )
                coarse_fps = [high_fps, pref_fps, low_fps]
                coarse_batch = _eval_fps_candidates(width, coarse_fps)
                coarse_fit = []
                coarse_nonfit = []
                for fps in sorted(set(coarse_fps), reverse=True):
                    p = coarse_batch.get(fps)
                    if not p:
                        continue
                    if _fits_target(p):
                        coarse_fit.append((fps, p))
                    else:
                        coarse_nonfit.append((fps, p))

                if coarse_fit and coarse_fit[0][0] >= high_fps:
                    return coarse_fit[0][1], coarse_fit[0][0]

                low_path = coarse_batch.get(low_fps)
                if not (low_path and _fits_target(low_path)):
                    return None
                low_size = _path_size(low_path)
                if low_size is not None and low_size > (
                    target_bytes * width_prune_ratio
                ):
                    logging.debug(
                        "[shrink] prune width=%s: low_fps size=%s over ratio %.2f",
                        str(width),
                        str(low_size),
                        width_prune_ratio,
                    )
                    return None

                if coarse_fit:
                    best_fit_fps, best_fit_path = max(coarse_fit, key=lambda x: x[0])
                else:
                    best_fit_fps, best_fit_path = low_fps, low_path

                nonfit_above = [fps for fps, _ in coarse_nonfit if fps > best_fit_fps]
                if nonfit_above:
                    hi = min(nonfit_above) - 1
                else:
                    hi = high_fps - 1
                lo = best_fit_fps + 1
                while lo <= hi:
                    if _time_budget_exceeded():
                        break
                    mid = (lo + hi) // 2
                    mid_path = _produce(width, mid)
                    if not mid_path:
                        hi = mid - 1
                        continue
                    if _fits_target(mid_path):
                        best_fit_path = mid_path
                        best_fit_fps = mid
                        lo = mid + 1
                    else:
                        hi = mid - 1
                return best_fit_path, best_fit_fps

            def _probe_gif_width(path):
                reader = None
                try:
                    import imageio

                    reader = imageio.get_reader(path)
                    frame = reader.get_next_data()
                    if getattr(frame, "shape", None) and len(frame.shape) >= 2:
                        return int(frame.shape[1])
                except Exception:
                    return None
                finally:
                    try:
                        if reader is not None:
                            reader.close()
                    except Exception:
                        pass
                return None

            src_width = _probe_gif_width(gif_path)
            hi_width = int(src_width) if src_width else 800
            min_width_effective = min_width if hi_width >= min_width else hi_width
            source_tag = "mp4" if ffmpeg_input != gif_path else "gif"
            cache_key = (
                f"{source_tag}_w{hi_width}_t{int(target_bytes)}"
                f"_b{int(orig_size // (256 * 1024))}"
            )
            size_bucket_now = int(orig_size // (256 * 1024))
            coarse_width = int((hi_width // 160) * 160)
            if coarse_width <= 0:
                coarse_width = hi_width
            coarse_target = int((int(target_bytes) // (1024 * 1024)) * (1024 * 1024))
            if coarse_target <= 0:
                coarse_target = int(target_bytes)
            coarse_cache_key = (
                f"{source_tag}_w{coarse_width}_t{coarse_target}_b{size_bucket_now}"
            )

            # Aggressive cache probing:
            # try recent successful params first (plus tiny fps tweaks),
            # then fall back to exact/coarse/neighbor key matches.
            try:
                recent_probe_limit = int(
                    os.environ.get("SHRINK_RECENT_PROBE_LIMIT", "8")
                )
            except Exception:
                recent_probe_limit = 8
            recent_probe_limit = max(2, min(20, recent_probe_limit))
            recent_candidates = []
            for recent_entry in _find_recent_cache_entries(
                source_tag, hi_width, int(target_bytes), size_bucket_now
            ):
                try:
                    rw = recent_entry.get("width")
                    rfps = int(recent_entry.get("fps", 10))
                except Exception:
                    continue
                recent_candidates.append((rw, rfps))
                recent_candidates.append((rw, rfps + 1))
                recent_candidates.append((rw, rfps - 1))
                if len(recent_candidates) >= recent_probe_limit:
                    break
            if recent_candidates:
                cached_path = _try_param_candidates(
                    recent_candidates[:recent_probe_limit],
                    "recent_probe",
                    cache_key,
                    alias_keys=[coarse_cache_key],
                )
                if cached_path:
                    name = os.path.splitext(os.path.basename(gif_path))[0]
                    dst = os.path.join(out_dir, f"{name}_small.gif")
                    shutil.move(cached_path, dst)
                    _emit_metrics("ok_cache", dst)
                    return dst

            with cache_io_lock:
                cached_entry = cache_data.get(cache_key)
            cached_path = _try_cached_entry(cached_entry, cache_key)
            if cached_path:
                metrics["cache_hit"] = "exact"
            if not cached_path:
                with cache_io_lock:
                    coarse_entry = cache_data.get(coarse_cache_key)
                cached_path = _try_cached_entry(coarse_entry, cache_key)
                if cached_path:
                    metrics["cache_hit"] = "coarse"
                    logging.debug(
                        "[shrink] cache coarse-hit: key=%s from=%s",
                        cache_key,
                        coarse_cache_key,
                    )
            if not cached_path:
                near_key, near_entry = _find_neighbor_cache_entry(
                    source_tag, hi_width, int(target_bytes), size_bucket_now
                )
                if near_entry is not None:
                    cached_path = _try_cached_entry(near_entry, cache_key)
                    if cached_path:
                        metrics["cache_hit"] = "neighbor"
                        logging.debug(
                            "[shrink] cache near-hit: key=%s from=%s",
                            cache_key,
                            near_key,
                        )
            if not cached_path:
                for recent_entry in _find_recent_cache_entries(
                    source_tag, hi_width, int(target_bytes), size_bucket_now
                ):
                    if _time_budget_exceeded():
                        break
                    cached_path = _try_cached_entry(recent_entry, cache_key)
                    if cached_path:
                        metrics["cache_hit"] = "recent"
                        logging.debug("[shrink] cache recent-hit: key=%s", cache_key)
                        break
            if cached_path:
                name = os.path.splitext(os.path.basename(gif_path))[0]
                dst = os.path.join(out_dir, f"{name}_small.gif")
                shutil.move(cached_path, dst)
                _emit_metrics("ok_cache", dst)
                return dst

            # Width-first search:
            # 1) coarse/binary search max width that can fit at low FPS
            # 2) run FPS fine search only once on the selected width
            low_fps = 5

            def _width_fits_at_low_fps(width):
                p = _produce(width, low_fps)
                if not p:
                    return False
                if not _fits_target(p):
                    return False
                s = _path_size(p)
                if s is not None and s > (target_bytes * width_prune_ratio):
                    return False
                return True

            selected_width = None

            # Try original width first at low FPS (best quality if it fits).
            orig_low_fit = _width_fits_at_low_fps(None)
            if orig_low_fit:
                selected_width = None
            elif _width_fits_at_low_fps(min_width_effective):
                # Binary search the largest width that still fits at low FPS.
                best_width = min_width_effective
                lo = min_width_effective + 1
                hi = hi_width
                while lo <= hi:
                    if _time_budget_exceeded():
                        break
                    mid = (lo + hi) // 2
                    if _width_fits_at_low_fps(mid):
                        best_width = mid
                        lo = mid + 1
                    else:
                        hi = mid - 1
                selected_width = best_width

            if selected_width is not None or orig_low_fit:
                final_fit = _best_fps_path_for_width(selected_width)
                if final_fit:
                    final_path, final_fps = final_fit
                    name = os.path.splitext(os.path.basename(gif_path))[0]
                    dst = os.path.join(out_dir, f"{name}_small.gif")
                    shutil.move(final_path, dst)
                    _cache_set(
                        cache_key,
                        selected_width,
                        final_fps,
                        alias_keys=[coarse_cache_key],
                    )
                    _emit_metrics("ok_ffmpeg", dst)
                    return dst

        base_input = (
            best_candidate
            if best_candidate and os.path.exists(best_candidate)
            else gif_path
        )

        try:
            max_gifsicle_variants = int(
                os.environ.get("SHRINK_MAX_GIFSICLE_VARIANTS", "8")
            )
        except Exception:
            max_gifsicle_variants = 8
        max_gifsicle_variants = max(1, max_gifsicle_variants)
        gifsicle_variants_tried = 0
        try:
            gifsicle_early_stop_min_improve = float(
                os.environ.get("SHRINK_GIFSICLE_EARLY_STOP_MIN_IMPROVE", "0.02")
            )
        except Exception:
            gifsicle_early_stop_min_improve = 0.02
        try:
            gifsicle_early_stop_streak_limit = int(
                os.environ.get("SHRINK_GIFSICLE_EARLY_STOP_STREAK", "2")
            )
        except Exception:
            gifsicle_early_stop_streak_limit = 2
        gifsicle_early_stop_min_improve = max(0.0, gifsicle_early_stop_min_improve)
        gifsicle_early_stop_streak_limit = max(1, gifsicle_early_stop_streak_limit)
        gifsicle_last_oversize = None
        gifsicle_low_improve_streak = 0
        gifsicle_early_stop = False

        def _update_gifsicle_early_stop(size: Optional[int]) -> None:
            nonlocal gifsicle_last_oversize
            nonlocal gifsicle_low_improve_streak
            nonlocal gifsicle_early_stop
            if size is None or size <= target_bytes:
                return
            prev = gifsicle_last_oversize
            if prev is not None and prev > 0 and size < prev:
                improve = float(prev - size) / float(prev)
                if improve < gifsicle_early_stop_min_improve:
                    gifsicle_low_improve_streak += 1
                else:
                    gifsicle_low_improve_streak = 0
            else:
                gifsicle_low_improve_streak = 0
            gifsicle_last_oversize = size
            if gifsicle_low_improve_streak >= gifsicle_early_stop_streak_limit:
                gifsicle_early_stop = True
                metrics["gifsicle_early_stop"] = True
                logging.debug(
                    "[shrink] gifsicle early-stop triggered: "
                    "low improvement streak reached"
                )

        # gifsicle color reductions
        if gifsicle_exe:
            for colors in (256, 128, 64, 32, 16, 8):
                if (
                    _time_budget_exceeded()
                    or
                    gifsicle_early_stop
                    or gifsicle_variants_tried >= max_gifsicle_variants
                ):
                    break
                out_gif = os.path.join(tmpdir, f"g_colors_{colors}.gif")
                try:
                    gifsicle_variants_tried += 1
                    metrics["gifsicle_variants"] = gifsicle_variants_tried
                    _run_cmd_timed(
                        [
                            gifsicle_exe,
                            "-O3",
                            "--colors",
                            str(colors),
                            base_input,
                            "-o",
                            out_gif,
                        ],
                        check=True,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                    if _consider(out_gif):
                        name = os.path.splitext(os.path.basename(gif_path))[0]
                        dst = os.path.join(out_dir, f"{name}_small.gif")
                        shutil.move(out_gif, dst)
                        _emit_metrics("ok_gifsicle", dst)
                        return dst
                    try:
                        _update_gifsicle_early_stop(os.path.getsize(out_gif))
                    except Exception:
                        pass
                except Exception:
                    continue

        # gifsicle lossy fallback (disabled by default to preserve quality).
        # Enable only when needed via SHRINK_ENABLE_GIFSICLE_LOSSY=1.
        enable_gifsicle_lossy = (
            str(os.environ.get("SHRINK_ENABLE_GIFSICLE_LOSSY", "0")).strip().lower()
            in ("1", "true", "yes", "on")
        )
        if gifsicle_exe and enable_gifsicle_lossy:
            for lossy in (40, 80, 120, 160, 200, 300, 400):
                if (
                    _time_budget_exceeded()
                    or
                    gifsicle_early_stop
                    or gifsicle_variants_tried >= max_gifsicle_variants
                ):
                    break
                out_gif = os.path.join(tmpdir, f"g_lossy_{lossy}.gif")
                try:
                    gifsicle_variants_tried += 1
                    metrics["gifsicle_variants"] = gifsicle_variants_tried
                    _run_cmd_timed(
                        [
                            gifsicle_exe,
                            "-O3",
                            f"--lossy={lossy}",
                            base_input,
                            "-o",
                            out_gif,
                        ],
                        check=True,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                    if _consider(out_gif):
                        name = os.path.splitext(os.path.basename(gif_path))[0]
                        dst = os.path.join(out_dir, f"{name}_small.gif")
                        shutil.move(out_gif, dst)
                        _emit_metrics("ok_gifsicle", dst)
                        return dst
                    try:
                        _update_gifsicle_early_stop(os.path.getsize(out_gif))
                    except Exception:
                        pass
                except Exception:
                    continue

        # move best candidate if exists
        if best_candidate and os.path.exists(best_candidate):
            name = os.path.splitext(os.path.basename(gif_path))[0]
            dst = os.path.join(out_dir, f"{name}_small_best.gif")
            try:
                shutil.move(best_candidate, dst)
                _emit_metrics("partial_best", dst)
                return dst
            except Exception:
                _emit_metrics("final_move_failed")
                return None

    finally:
        try:
            for p in os.listdir(tmpdir):
                fp = os.path.join(tmpdir, p)
                try:
                    if os.path.exists(fp):
                        os.remove(fp)
                except Exception:
                    pass
            try:
                os.rmdir(tmpdir)
            except Exception:
                pass
        except Exception:
            pass

    _emit_metrics("no_result")
    return None
