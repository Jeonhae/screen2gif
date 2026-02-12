import os
import time
import shutil
import subprocess
import tempfile
import logging
from typing import Optional

try:
    import imageio_ffmpeg
except Exception:
    imageio_ffmpeg = None

from src.utils.logging_config import append_diagnostic
try:
    from utils import run_hidden
except Exception:
    # If importing top-level utils fails (package context), provide a local passthrough.
    def run_hidden(cmd, **kwargs):
        return subprocess.run(cmd, **kwargs)


def shrink_gif_to_target(gif_path: str, target_bytes: int, out_dir: str) -> Optional[str]:
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

    logging.debug(f"[shrink] orig_size={orig_size} target_bytes={target_bytes}")

    # Allow forcing a specific ffmpeg executable via env var for testing/packaging.
    # Prefer: env var -> system ffmpeg -> repo/bin/ffmpeg -> imageio_ffmpeg
    ffmpeg_exe = os.environ.get("SHRINK_FFMPEG_EXE")
    if ffmpeg_exe and not os.path.exists(ffmpeg_exe):
        ffmpeg_exe = None
    if not ffmpeg_exe:
        ffmpeg_exe = shutil.which("ffmpeg")
    if not ffmpeg_exe:
        try:
            from pathlib import Path

            repo_root = Path(__file__).resolve().parents[2]
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
        def _run_cmd_timed(cmd, **kwargs):
            t0 = time.perf_counter()
            try:
                run_hidden(cmd, **kwargs)
            finally:
                t1 = time.perf_counter()
                try:
                    append_diagnostic(
                        "shrink_perf.txt",
                        f"{time.time()} cmd={' '.join(cmd)} duration_ms={(t1-t0)*1000:.1f}\n",
                    )
                except Exception:
                    pass

        if ffmpeg_exe:
            # Two-phase strategy: quick attempts first, then aggressive if needed.
            quick_fps = [10, 8]
            quick_widths = [320, 480, 640, None]
            quick_max = int(os.environ.get("SHRINK_QUICK_MAX_FFMPEG_ATTEMPTS", "6"))

            agg_fps = [15, 12, 10, 8, 6, 5]
            agg_widths = [None, 800, 640, 480, 320]
            agg_max = int(os.environ.get("SHRINK_AGGRESSIVE_MAX_FFMPEG_ATTEMPTS", "20"))

            def _run_phase(fps_list, width_list, max_attempts):
                attempts = 0
                for fps in fps_list:
                    for width in width_list:
                        palette = os.path.join(tmpdir, f'palette_{fps}_{width or "orig"}.png')
                        out_gif = os.path.join(tmpdir, f'ff_{fps}_{width or "orig"}.gif')
                        scale_expr = (f"scale={width}:-1:flags=lanczos" if width else "scale=iw:ih:flags=lanczos")
                        try:
                            attempts += 1
                            if attempts > max_attempts:
                                raise RuntimeError("max ffmpeg attempts reached")
                            _run_cmd_timed([
                                ffmpeg_exe,
                                "-y",
                                "-i",
                                gif_path,
                                "-vf",
                                ("fps=" + str(fps) + "," + scale_expr + ",palettegen"),
                                palette,
                            ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                            _run_cmd_timed([
                                ffmpeg_exe,
                                "-y",
                                "-i",
                                gif_path,
                                "-i",
                                palette,
                                "-lavfi",
                                ("fps=" + str(fps) + "," + scale_expr + "[x];" "[x][1:v]paletteuse=dither=bayer"),
                                out_gif,
                            ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                            if _consider(out_gif):
                                name = os.path.splitext(os.path.basename(gif_path))[0]
                                dst = os.path.join(out_dir, f"{name}_small.gif")
                                shutil.move(out_gif, dst)
                                return True
                        except Exception:
                            if attempts > max_attempts:
                                return False
                            continue
                return False

            done = _run_phase(quick_fps, quick_widths, quick_max)
            if not done:
                _run_phase(agg_fps, agg_widths, agg_max)

        base_input = (best_candidate if best_candidate and os.path.exists(best_candidate) else gif_path)

        if gifsicle_exe:
            for colors in (256, 128, 64, 32, 16, 8):
                out_gif = os.path.join(tmpdir, f"g_colors_{colors}.gif")
                try:
                    _run_cmd_timed([
                        gifsicle_exe,
                        "-O3",
                        "--colors",
                        str(colors),
                        base_input,
                        "-o",
                        out_gif,
                    ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    if _consider(out_gif):
                        name = os.path.splitext(os.path.basename(gif_path))[0]
                        dst = os.path.join(out_dir, f"{name}_small.gif")
                        shutil.move(out_gif, dst)
                        return dst
                except Exception:
                    continue

        if gifsicle_exe:
            for lossy in (40, 80, 120, 160, 200, 300, 400):
                out_gif = os.path.join(tmpdir, f"g_lossy_{lossy}.gif")
                try:
                    _run_cmd_timed([
                        gifsicle_exe,
                        "-O3",
                        f"--lossy={lossy}",
                        base_input,
                        "-o",
                        out_gif,
                    ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    if _consider(out_gif):
                        name = os.path.splitext(os.path.basename(gif_path))[0]
                        dst = os.path.join(out_dir, f"{name}_small.gif")
                        shutil.move(out_gif, dst)
                        return dst
                except Exception:
                    continue

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
