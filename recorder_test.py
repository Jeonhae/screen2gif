import time

import recorder


def test_start_returns_quickly_when_mss_init_fails(monkeypatch):
    def _boom():
        raise RuntimeError("mss init failed")

    monkeypatch.setattr(recorder.mss, "mss", _boom)

    rec = recorder.ScreenRecorder()
    t0 = time.perf_counter()
    ok = rec.start((0, 0, 100, 80), fps=10, out_path="video/out.mp4", startup_timeout=2.0)
    elapsed = time.perf_counter() - t0

    assert ok is False
    assert elapsed < 1.0
    assert rec.is_recording() is False
