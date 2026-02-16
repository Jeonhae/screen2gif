import os
import subprocess
import logging
import time
import uuid
import imageio

from utils import resolve_ffmpeg_exe


def convert_mp4_to_gif(mp4_path: str, gif_path: str, fps: int = 10) -> bool:
    """Convert an MP4 to GIF using ffmpeg when available, otherwise imageio.

    Returns True on success, False on failure.
    """
    # Use ffmpeg when available for quality
    ffmpeg_exe = resolve_ffmpeg_exe()
    ffmpeg_failed = False
    if ffmpeg_exe:
        ffmpeg_cmd = ffmpeg_exe
        tmp_root = os.path.join(os.path.dirname(__file__), "tmp_ffmpeg")
        os.makedirs(tmp_root, exist_ok=True)
        palette_path = os.path.join(
            tmp_root,
            f"palette_{uuid.uuid4().hex}.png",
        )
        gen_palette_cmd = [
            ffmpeg_cmd,
            "-y",
            "-i",
            mp4_path,
            "-vf",
            f"fps={fps},scale=iw:ih:flags=lanczos,palettegen",
            palette_path,
        ]
        gif_cmd = [
            ffmpeg_cmd,
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
            gen_res = subprocess.run(
                gen_palette_cmd,
                capture_output=True,
                text=True,
            )
            if gen_res.returncode != 0:
                logging.error(
                    "ffmpeg palette generation failed (code=%s): %s",
                    gen_res.returncode,
                    (gen_res.stderr or "").strip()[-1000:],
                )
                ffmpeg_failed = True
            else:
                gif_res = subprocess.run(
                    gif_cmd,
                    capture_output=True,
                    text=True,
                )
                if gif_res.returncode != 0:
                    logging.error(
                        "ffmpeg gif conversion failed (code=%s): %s",
                        gif_res.returncode,
                        (gif_res.stderr or "").strip()[-1000:],
                    )
                    ffmpeg_failed = True
                else:
                    return True

        except OSError:
            logging.exception("Failed to execute ffmpeg")
            ffmpeg_failed = True
        except Exception:
            logging.exception("Unexpected ffmpeg conversion error")
            ffmpeg_failed = True
        finally:
            for _ in range(3):
                try:
                    if os.path.exists(palette_path):
                        os.remove(palette_path)
                    break
                except PermissionError:
                    # ffmpeg can keep the handle briefly on Windows.
                    time.sleep(0.05)
                except Exception:
                    logging.exception("Failed to remove temporary ffmpeg palette file")
                    break

    if ffmpeg_failed:
        logging.warning("ffmpeg conversion failed; falling back to imageio")
        # Remove any partially-created gif file so the imageio fallback
        # can write a fresh output without colliding with remnants from
        # the failed ffmpeg attempt.
        try:
            if os.path.exists(gif_path):
                try:
                    os.remove(gif_path)
                except Exception:
                    # Best-effort removal; if removal fails, continue to fallback
                    logging.debug("Failed to remove partial gif before fallback")
        except Exception:
            logging.exception("Error while attempting to cleanup partial gif")

    # Fallback: use imageio to read video and write GIF
    reader = None
    writer = None
    try:
        reader = imageio.get_reader(mp4_path)
        writer = imageio.get_writer(gif_path, mode="I", fps=fps)
        frame_count = 0
        for frame in reader:
            writer.append_data(frame)
            frame_count += 1
        return frame_count > 0
    except Exception:
        logging.exception("imageio fallback conversion failed")
        return False
    finally:
        try:
            if writer is not None:
                writer.close()
        except Exception:
            logging.exception("Failed to close imageio writer")
        try:
            if reader is not None:
                reader.close()
        except Exception:
            logging.exception("Failed to close imageio reader")
