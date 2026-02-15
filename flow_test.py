from types import SimpleNamespace
import logging

import main


class _DummyOverlay:
    def __init__(self):
        self.stopped = False
        self.started = False
        self.hidden = False

    def start_recording(self):
        self.started = True

    def stop_recording(self):
        self.stopped = True

    def hide(self):
        self.hidden = True


class _DummyToolbar:
    def __init__(self):
        self.hidden = False

    def hide(self):
        self.hidden = True


class _DummyVisibility:
    def __init__(self):
        self.started = False
        self.stopped = False

    def start(self):
        self.started = True

    def stop(self):
        self.stopped = True


class _DummyRecorder:
    def __init__(self, start_ret=True, is_recording_ret=True, stop_ret=("x.mp4", True)):
        self.start_ret = start_ret
        self.is_recording_ret = is_recording_ret
        self.stop_ret = stop_ret
        self.start_calls = []
        self.stop_calls = []

    def start(self, rect, fps=10, out_path=None, **kwargs):
        self.start_calls.append((rect, fps, out_path, kwargs))
        return self.start_ret

    def is_recording(self):
        return self.is_recording_ret

    def stop(self, timeout=5.0):
        self.stop_calls.append(timeout)
        return self.stop_ret


def _build_ctx(recorder):
    return SimpleNamespace(
        overlay=_DummyOverlay(),
        toolbar=_DummyToolbar(),
        recorder=recorder,
        visibility_monitor=_DummyVisibility(),
        conversion_in_progress=False,
        conversion_worker=None,
        conversion_thread=None,
        dispatcher=main.MainThreadDispatcher(),
        return_to_main=lambda: None,
    )


def test_start_flow_blocks_while_conversion_running(monkeypatch):
    recorder = _DummyRecorder()
    ctx = _build_ctx(recorder)
    ctx.conversion_in_progress = True
    shown = []

    monkeypatch.setattr(main, "show_topmost_message", lambda *a, **k: shown.append(a))
    main.start_recording_flow(ctx, (1, 2, 3, 4))

    assert shown, "Expected an informational dialog when conversion is in progress"
    assert recorder.start_calls == []


def test_stop_flow_skips_conversion_if_recorder_not_stopped(monkeypatch):
    recorder = _DummyRecorder(stop_ret=("video/out.mp4", False))
    ctx = _build_ctx(recorder)
    calls = {"msg": 0, "return_main": 0}

    def _msg(*args, **kwargs):
        calls["msg"] += 1
        return None

    def _mark_return_main():
        calls["return_main"] = calls["return_main"] + 1

    ctx.return_to_main = _mark_return_main
    monkeypatch.setattr(main, "show_topmost_message", _msg)

    main.stop_recording_flow(ctx)

    assert calls["msg"] >= 1
    assert calls["return_main"] == 1
    assert ctx.conversion_in_progress is False


def test_finalize_conversion_result_resets_state(monkeypatch):
    calls = {"msg": 0, "return_main": 0}
    ctx = SimpleNamespace(
        conversion_in_progress=True,
        conversion_worker=object(),
        conversion_thread=None,
        return_to_main=lambda: calls.__setitem__(
            "return_main",
            calls["return_main"] + 1,
        ),
    )

    monkeypatch.setattr(main, "copy_path_to_clipboard", lambda _p: True)
    monkeypatch.setattr(
        main,
        "show_topmost_message",
        lambda *a, **k: calls.__setitem__("msg", calls["msg"] + 1),
    )

    main._finalize_conversion_result(
        ctx,
        {"ok": True, "gif_path": "gif/out.gif", "error": None},
    )

    assert ctx.conversion_in_progress is False
    assert ctx.conversion_worker is None
    assert ctx.conversion_thread is None
    assert calls["msg"] == 1
    assert calls["return_main"] == 1


def test_start_flow_logs_clear_video_errors(monkeypatch, caplog):
    recorder = _DummyRecorder(start_ret=True, is_recording_ret=True)
    ctx = _build_ctx(recorder)

    monkeypatch.setattr(main, "clear_video_folder", lambda: ([], [("video/x.mp4", "denied")]))
    monkeypatch.setattr(main, "_process_ui_events_wait", lambda _ms=120: None)

    with caplog.at_level(logging.WARNING):
        main.start_recording_flow(ctx, (1, 2, 100, 80))

    assert recorder.start_calls
    assert any("clear_video_folder had" in rec.message for rec in caplog.records)
