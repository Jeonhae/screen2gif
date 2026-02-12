"""Create a tiny sample GIF for tests (writes to screen2gif/gif/sample_test.gif)."""
import base64
import os


def main():
    b64 = b"R0lGODlhAQABAPAAAP///wAAACH5BAAAAAAALAAAAAABAAEAAAICRAEAOw=="
    data = base64.b64decode(b64)
    out_dir = os.path.join(os.path.dirname(__file__), "..", "gif")
    out_dir = os.path.abspath(out_dir)
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "sample_test.gif")
    with open(out_path, "wb") as f:
        f.write(data)
    print("Wrote sample GIF:", out_path)


if __name__ == "__main__":
    main()
