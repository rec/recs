import pytest

from recs.base.types import RecordKeys
from recs.cfg.cfg import Cfg
from recs.ui import key_events


def test_terminal_key_recorder_is_disabled_on_windows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(key_events.sys, 'platform', 'win32')
    recorder = key_events.TerminalKeyRecorder()

    recorder.start()

    assert not recorder.running


def test_local_key_capture_uses_terminal_recorder(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr('recs.cfg.cfg._pynput_available', lambda: True)

    recorder = key_events.make_key_recorder(Cfg(record_keys=RecordKeys.press))

    assert isinstance(recorder, key_events.TerminalKeyRecorder)


def test_explicit_global_key_capture_uses_pynput(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr('recs.cfg.cfg._pynput_available', lambda: True)

    recorder = key_events.make_key_recorder(
        Cfg(record_keys=RecordKeys.press, record_key_all_apps=True)
    )

    assert isinstance(recorder, key_events.PynputKeyRecorder)
