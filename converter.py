import shutil
import subprocess
import imageio


def has_ffmpeg() -> bool:
    return shutil.which("ffmpeg") is not None


def convert_mp4_to_gif(mp4_path: str, gif_path: str, fps: int = 10) -> bool:
    """Convert an MP4 to GIF using ffmpeg when available, otherwise imageio.

    Returns True on success, False on failure.
    """
    # Use ffmpeg when available for quality
    if has_ffmpeg():
        cmd = [
            "ffmpeg",
            "-y",
            "-i",
            mp4_path,
            "-vf",
            f"fps={fps},scale=iw:ih:flags=lanczos",
            "-loop",
            "0",
            gif_path,
        ]
        try:
            subprocess.run(
                cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
            return True
        except subprocess.CalledProcessError:
            return False

    # Fallback: use imageio to read video and write GIF
    try:
        reader = imageio.get_reader(mp4_path)
        frames = [frame for frame in reader]
        if not frames:
            return False
        imageio.mimsave(gif_path, frames, fps=fps)
        return True
    except Exception:
        return False
