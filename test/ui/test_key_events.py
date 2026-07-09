import pytest

from recs.ui import key_events


def test_terminal_key_recorder_is_disabled_on_windows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(key_events.sys, 'platform', 'win32')
    recorder = key_events.TerminalKeyRecorder()

    recorder.start()

    assert not recorder.running
