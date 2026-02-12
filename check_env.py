import os
import shutil

p = r"d:\myCode\screen2gif\gif\20260204_155858.gif"
print("exists", os.path.exists(p))
print("size", os.path.getsize(p) if os.path.exists(p) else "N/A")
print("ffmpeg in PATH ->", shutil.which("ffmpeg"))
print("gifsicle in PATH ->", shutil.which("gifsicle"))
try:
    import imageio_ffmpeg

    print("imageio_ffmpeg.get_ffmpeg_exe ->", imageio_ffmpeg.get_ffmpeg_exe())
except Exception as e:
    print("imageio_ffmpeg import failed ->", e)
