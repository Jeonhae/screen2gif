import os
import time
import shutil
import subprocess
import tempfile
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Tuple
import logging

try:
    import imageio_ffmpeg
except Exception:
    imageio_ffmpeg = None


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
    # 2. System `ffmpeg` on PATH
    # 3. Repo-local `bin/ffmpeg` (useful for bundled binaries)
    # 4. imageio_ffmpeg bundled executable
    ffmpeg_exe = os.environ.get("SHRINK_FFMPEG_EXE")
    if ffmpeg_exe and not os.path.exists(ffmpeg_exe):
        ffmpeg_exe = None
    if not ffmpeg_exe:
        ffmpeg_exe = shutil.which("ffmpeg")
    if not ffmpeg_exe:
        try:
            repo_root = Path(__file__).resolve().parents[1]
            candidate = repo_root / "bin" / ("ffmpeg.exe" if os.name == "nt" else "ffmpeg")
            if candidate.exists():
                ffmpeg_exe = str(candidate)
        except Exception:
            pass
    if not ffmpeg_exe and imageio_ffmpeg is not None:
        try:
            exe = imageio_ffmpeg.get_ffmpeg_exe()
            if exe:
                ffmpeg_exe = exe
        except Exception:
            pass
    gifsicle_exe = shutil.which("gifsicle")
    logging.debug(f"[shrink] ffmpeg_exe={ffmpeg_exe} gifsicle_exe={gifsicle_exe}")

    tmpdir = tempfile.mkdtemp(prefix="shrink_gif_")
    best_candidate: Optional[str] = None
    best_size: Optional[int] = None

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
            fps_list = [15, 12, 10, 8, 6, 5]
            width_list = [None, 800, 640, 480, 320]
            for fps in fps_list:
                for width in width_list:
                    palette = os.path.join(
                        tmpdir, f'palette_{fps}_{width or "orig"}.png'
                    )
                    out_gif = os.path.join(tmpdir, f'ff_{fps}_{width or "orig"}.gif')
                    scale_expr = (
                        f"scale={width}:-1:flags=lanczos"
                        if width
                        else "scale=iw:ih:flags=lanczos"
                    )
                    try:
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
                        if _consider(out_gif):
                            name = os.path.splitext(os.path.basename(gif_path))[0]
                            dst = os.path.join(out_dir, f"{name}_small.gif")
                            shutil.move(out_gif, dst)
                            return dst
                    except Exception:
                        continue

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
