import ctypes
import struct
import os
from datetime import datetime
import glob
import pytest

kernel32 = ctypes.windll.kernel32
user32 = ctypes.windll.user32


def log(msg):
    print(f"[{datetime.now()}] {msg}")


def test(path):
    full = os.path.abspath(path)
    files_utf16 = full.encode("utf-16le") + b"\x00\x00"
    pFiles = 20
    pt_x = 0
    pt_y = 0
    fNC = 0
    fWide = 1
    header = struct.pack("<IiiII", pFiles, pt_x, pt_y, fNC, fWide)
    data = header + files_utf16 + b"\x00\x00"
    size = len(data)
    log(f"data size={size}")

    GMEM_MOVEABLE = 0x0002
    GMEM_ZEROINIT = 0x0040
    flags = GMEM_MOVEABLE | GMEM_ZEROINIT

    h = kernel32.GlobalAlloc(flags, size)
    err = kernel32.GetLastError()
    log(f"GlobalAlloc h={h} GetLastError={err}")
    assert h, "GlobalAlloc failed"
    lp = kernel32.GlobalLock(h)
    err = kernel32.GetLastError()
    log(f"GlobalLock lp={lp} GetLastError={err}")
    if not lp:
        kernel32.GlobalFree(h)
        pytest.fail("GlobalLock failed")
    # copy
    ctypes.memmove(lp, data, size)
    kernel32.GlobalUnlock(h)
    # open clipboard
    if not user32.OpenClipboard(0):
        log("OpenClipboard failed")
        kernel32.GlobalFree(h)
        pytest.fail("OpenClipboard failed")
    try:
        user32.EmptyClipboard()
        CF_HDROP = 15
        r = user32.SetClipboardData(CF_HDROP, h)
        err = kernel32.GetLastError()
        log(f"SetClipboardData ret={r} GetLastError={err}")
        if not r:
            kernel32.GlobalFree(h)
            pytest.fail("SetClipboardData failed")
        return
    finally:
        user32.CloseClipboard()


if __name__ == "__main__":
    files = glob.glob("screen2gif/gif/*.gif")
    if not files:
        print("no gif")
    else:
        print("testing", files[-1])
        ok = test(files[-1])
        print("ok=", ok)


@pytest.fixture
def path():
    # prefer explicit sample gif created by scripts, otherwise pick latest
    candidate = os.path.join("screen2gif", "gif", "sample_test.gif")
    if os.path.exists(candidate):
        return candidate
    files = glob.glob("screen2gif/gif/*.gif")
    if not files:
        pytest.skip("no gif available for cfhdrop_test")
    return files[-1]
