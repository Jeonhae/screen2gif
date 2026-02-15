import os
import time
import shutil
import subprocess
import tempfile
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Tuple
import logging

# Do not use imageio_ffmpeg fallback - prefer repo/bin/ffmpeg or system ffmpeg.


def ensure_dirs(base_dir=None):
    base = base_dir or os.path.dirname(__file__)
    for d in ("video", "gif", "logs"):
        p = os.path.join(base, d)
        os.makedirs(p, exist_ok=True)


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


def clear_gif_folder(base_dir: Optional[str] = None) -> Tuple[List[str], List[Tuple[str, str]]]:
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
    gif_path: str, target_bytes: int, out_dir: str
) -> Optional[str]:
    """Reduce `gif_path` to be <= `target_bytes` and place result in `out_dir`.

    Returns path to produced GIF in `out_dir` on success, otherwise None.
    """
    if not os.path.exists(gif_path):
        return None

    os.makedirs(out_dir, exist_ok=True)

    try:
        orig_size = os.path.getsize(gif_path)
    except Exception:
        return None

    if orig_size <= target_bytes:
        dst = os.path.join(out_dir, os.path.basename(gif_path))
        shutil.copy2(gif_path, dst)
        return dst

    # debug info
    logging.debug(f"[shrink] orig_size={orig_size} target_bytes={target_bytes}")

    # Order of preference for ffmpeg executable:
    # 1. Environment variable `SHRINK_FFMPEG_EXE`
    # 2. Repo-local `bin/ffmpeg` (preferred)
    # 3. System `ffmpeg` on PATH
    ffmpeg_exe = os.environ.get("SHRINK_FFMPEG_EXE")
    if ffmpeg_exe and not os.path.exists(ffmpeg_exe):
        ffmpeg_exe = None

    if not ffmpeg_exe:
        # Check common repo-relative bin locations robustly
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
    # Prefer repo/bin/gifsicle, then env var SHRINK_GIFSICLE_EXE, then system gifsicle
    gifsicle_exe = os.environ.get("SHRINK_GIFSICLE_EXE")
    if gifsicle_exe and not os.path.exists(gifsicle_exe):
        gifsicle_exe = None
    if not gifsicle_exe:
        try:
            file_path = Path(__file__).resolve()
            candidates = [file_path.parent / "bin", file_path.parent.parent / "bin", file_path.parent.parent.parent / "bin"]
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
                subprocess.run(cmd, **kwargs)
            finally:
                t1 = time.perf_counter()
                try:
                    dbgdir = os.path.join(os.path.dirname(__file__), "logs")
                    os.makedirs(dbgdir, exist_ok=True)
                    with open(os.path.join(dbgdir, "shrink_perf.txt"), "a", encoding="utf-8") as pf:
                        pf.write(f"{time.time()} cmd={' '.join(cmd)} duration_ms={(t1-t0)*1000:.1f}\n")
                except Exception:
                    pass

        if ffmpeg_exe:
            min_width = 320
            produced = {}
            palette_cache = {}
            try:
                max_ffmpeg_variants = int(
                    os.environ.get("SHRINK_MAX_FFMPEG_VARIANTS", "12")
                )
            except Exception:
                max_ffmpeg_variants = 12
            max_ffmpeg_variants = max(1, max_ffmpeg_variants)
            ffmpeg_variants_tried = [0]

            def _run_palette(width, fps):
                scale_expr = (
                    f"scale={width}:-1:flags=lanczos"
                    if width
                    else "scale=iw:ih:flags=lanczos"
                )
                tag = f'{fps}_{width or "orig"}'
                palette_key = str(width or "orig")
                palette = palette_cache.get(palette_key)
                if not palette:
                    palette = os.path.join(tmpdir, f"palette_{palette_key}.png")
                    _run_cmd_timed(
                        [
                            ffmpeg_exe,
                            "-y",
                            "-i",
                            gif_path,
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
                        gif_path,
                        "-i",
                        palette,
                        "-lavfi",
                        (
                            "fps=" + str(fps) + "," + scale_expr + "[x];"
                            "[x][1:v]paletteuse=dither=bayer"
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

            def _produce(width, fps):
                key = (width, fps)
                if key in produced:
                    return produced[key]
                if ffmpeg_variants_tried[0] >= max_ffmpeg_variants:
                    produced[key] = None
                    return None
                try:
                    ffmpeg_variants_tried[0] += 1
                    produced[key] = _run_palette(width, fps)
                except Exception:
                    produced[key] = None
                return produced[key]

            def _best_fps_path_for_width(width):
                high_fps = 15
                low_fps = 5

                high_path = _produce(width, high_fps)
                if high_path and _fits_target(high_path):
                    return high_path

                low_path = _produce(width, low_fps)
                if not (low_path and _fits_target(low_path)):
                    return None

                best_fit_path = low_path
                lo = low_fps + 1
                hi = high_fps - 1
                while lo <= hi:
                    mid = (lo + hi) // 2
                    mid_path = _produce(width, mid)
                    if not mid_path:
                        hi = mid - 1
                        continue
                    if _fits_target(mid_path):
                        best_fit_path = mid_path
                        lo = mid + 1
                    else:
                        hi = mid - 1
                return best_fit_path

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

            # First try original width (highest quality) with FPS binary search.
            best_orig = _best_fps_path_for_width(None)
            if best_orig:
                name = os.path.splitext(os.path.basename(gif_path))[0]
                dst = os.path.join(out_dir, f"{name}_small.gif")
                shutil.move(best_orig, dst)
                return dst

            src_width = _probe_gif_width(gif_path)
            hi_width = int(src_width) if src_width else 800
            min_width_effective = min_width if hi_width >= min_width else hi_width

            # If even the minimum width cannot satisfy target, fall through to gifsicle.
            low_fit = _best_fps_path_for_width(min_width_effective)
            if low_fit:
                best_width_path = low_fit
                lo = min_width_effective + 1
                hi = hi_width
                while lo <= hi:
                    mid = (lo + hi) // 2
                    mid_fit = _best_fps_path_for_width(mid)
                    if mid_fit:
                        best_width_path = mid_fit
                        lo = mid + 1
                    else:
                        hi = mid - 1

                name = os.path.splitext(os.path.basename(gif_path))[0]
                dst = os.path.join(out_dir, f"{name}_small.gif")
                shutil.move(best_width_path, dst)
                return dst

        base_input = (
            best_candidate
            if best_candidate and os.path.exists(best_candidate)
            else gif_path
        )

        # gifsicle color reductions
        if gifsicle_exe:
            for colors in (256, 128, 64, 32, 16, 8):
                out_gif = os.path.join(tmpdir, f"g_colors_{colors}.gif")
                try:
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
                        return dst
                except Exception:
                    continue

        # gifsicle lossy fallback
        if gifsicle_exe:
            for lossy in (40, 80, 120, 160, 200, 300, 400):
                out_gif = os.path.join(tmpdir, f"g_lossy_{lossy}.gif")
                try:
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
                        return dst
                except Exception:
                    continue

        # move best candidate if exists
        if best_candidate and os.path.exists(best_candidate):
            name = os.path.splitext(os.path.basename(gif_path))[0]
            dst = os.path.join(out_dir, f"{name}_small_best.gif")
            try:
                shutil.move(best_candidate, dst)
                return dst
            except Exception:
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

    return None
