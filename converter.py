import os
import shutil
import subprocess
import tempfile
import imageio


def has_ffmpeg() -> bool:
    return shutil.which("ffmpeg") is not None


def convert_mp4_to_gif(mp4_path: str, gif_path: str, fps: int = 10) -> bool:
    """Convert an MP4 to GIF using ffmpeg when available, otherwise imageio.

    Returns True on success, False on failure.
    """
    # Use ffmpeg when available for quality
    if has_ffmpeg():
        tmpdir = tempfile.mkdtemp(prefix="mp4_to_gif_")
        palette_path = os.path.join(tmpdir, "palette.png")
        gen_palette_cmd = [
            "ffmpeg",
            "-y",
            "-i",
            mp4_path,
            "-vf",
            f"fps={fps},scale=iw:ih:flags=lanczos,palettegen",
            palette_path,
        ]
        gif_cmd = [
            "ffmpeg",
            "-y",
            "-i",
            mp4_path,
            "-i",
            palette_path,
            "-lavfi",
            (
                f"fps={fps},scale=iw:ih:flags=lanczos[x];"
                "[x][1:v]paletteuse=dither=bayer"
            ),
            "-loop",
            "0",
            gif_path,
        ]
        try:
            subprocess.run(
                gen_palette_cmd,
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            subprocess.run(
                gif_cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
            return True
        except subprocess.CalledProcessError:
            return False
        finally:
            try:
                if os.path.exists(palette_path):
                    os.remove(palette_path)
            except Exception:
                pass
            try:
                os.rmdir(tmpdir)
            except Exception:
                pass

    # Fallback: use imageio to read video and write GIF
    reader = None
    try:
        reader = imageio.get_reader(mp4_path)
        frames = [frame for frame in reader]
        if not frames:
            return False
        imageio.mimsave(gif_path, frames, fps=fps)
        return True
    except Exception:
        return False
    finally:
        try:
            if reader is not None:
                reader.close()
        except Exception:
            pass
