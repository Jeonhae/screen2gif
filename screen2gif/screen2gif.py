"""Simple screenshot-to-GIF example script.

Usage:
    python screen2gif.py --duration 5 --fps 2 --output out.gif
"""
import time
import argparse

import imageio
import numpy as np
import pyautogui


def capture_to_gif(duration: float, fps: int, output: str, region=None):
    frames = []
    interval = 1.0 / fps
    end = time.time() + duration
    try:
        while time.time() < end:
            img = pyautogui.screenshot(region=region)
            frames.append(np.array(img))
            time.sleep(interval)
    except KeyboardInterrupt:
        print("Capture interrupted by user")

    if not frames:
        raise RuntimeError("No frames captured")

    # Save as animated GIF
    imageio.mimsave(output, frames, fps=fps)
    print(f"Saved {len(frames)} frames to {output}")


def main():
    parser = argparse.ArgumentParser(description="Capture screen to animated GIF")
    parser.add_argument("--duration", type=float, default=5.0, help="Duration in seconds")
    parser.add_argument("--fps", type=int, default=2, help="Frames per second")
    parser.add_argument("--output", type=str, default="out.gif", help="Output GIF path")
    parser.add_argument("--region", type=int, nargs=4, help="Region: left top width height")
    args = parser.parse_args()

    region = tuple(args.region) if args.region else None
    capture_to_gif(args.duration, args.fps, args.output, region)


if __name__ == "__main__":
    main()
