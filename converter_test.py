import converter
import logging


class _Reader:
    def __init__(self, frames):
        self._frames = frames
        self.closed = False

    def __iter__(self):
        return iter(self._frames)

    def close(self):
        self.closed = True


class _Writer:
    def __init__(self):
        self.frames = []
        self.closed = False

    def append_data(self, frame):
        self.frames.append(frame)

    def close(self):
        self.closed = True


def test_converter_fallback_streams_frames(monkeypatch):
    reader = _Reader([b"a", b"b", b"c"])
    writer = _Writer()

    monkeypatch.setattr(converter, "resolve_ffmpeg_exe", lambda: None)
    monkeypatch.setattr(converter.imageio, "get_reader", lambda _p: reader)
    monkeypatch.setattr(
        converter.imageio,
        "get_writer",
        lambda _p, mode="I", fps=10: writer,
    )

    ok = converter.convert_mp4_to_gif("in.mp4", "out.gif", fps=10)
    assert ok is True
    assert writer.frames == [b"a", b"b", b"c"]
    assert writer.closed is True
    assert reader.closed is True


def test_converter_fallback_returns_false_when_no_frames(monkeypatch):
    reader = _Reader([])
    writer = _Writer()

    monkeypatch.setattr(converter, "resolve_ffmpeg_exe", lambda: None)
    monkeypatch.setattr(converter.imageio, "get_reader", lambda _p: reader)
    monkeypatch.setattr(
        converter.imageio,
        "get_writer",
        lambda _p, mode="I", fps=10: writer,
    )

    ok = converter.convert_mp4_to_gif("in.mp4", "out.gif", fps=10)
    assert ok is False
    assert writer.frames == []
    assert writer.closed is True
    assert reader.closed is True


def test_converter_logs_when_ffmpeg_palette_fails(monkeypatch, caplog):
    class _RunResult:
        def __init__(self, returncode, stderr=""):
            self.returncode = returncode
            self.stderr = stderr

    monkeypatch.setattr(converter, "resolve_ffmpeg_exe", lambda: "ffmpeg")
    monkeypatch.setattr(
        converter.subprocess,
        "run",
        lambda *a, **k: _RunResult(1, "palette failed"),
    )

    with caplog.at_level(logging.ERROR):
        ok = converter.convert_mp4_to_gif("in.mp4", "out.gif", fps=10)

    assert ok is False
    assert any("palette generation failed" in rec.message for rec in caplog.records)
