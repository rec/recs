from pathlib import Path
from test.conftest import DEVICES_FILE

import pytest
from pydantic import ValidationError

from recs.base.types import RecordKeys
from recs.cfg import Cfg, cfg


def test_sdtype(mock_devices):
    Cfg(formats=['wav'], subtype='pcm_16', sdtype='int32')


def test_missing_files(mock_devices: None) -> None:
    with pytest.raises(ValidationError, match='Non-existent file: unknown.wav'):
        Cfg(files=['unknown.wav'])


def test_bad_devices(mock_devices):
    with pytest.raises(ValidationError, match='unknown.json does not exist'):
        Cfg(devices=Path('unknown.json'))


def test_empty_devices(tmp_path: Path, mock_devices: None) -> None:
    devices = tmp_path / 'devices.json'
    devices.write_text('[]')

    with pytest.raises(ValidationError, match='contains no devices'):
        Cfg(devices=devices)


def test_devices(mock_devices):
    cfg = Cfg(devices=DEVICES_FILE)
    assert cfg.input_devices


def test_gui_defaults_to_all_key_events(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cfg, '_pynput_available', lambda: False)

    c = Cfg(gui=True)

    assert c.keys.record_keys == RecordKeys.all
    assert c.keys.record_key_all_apps is True


def test_terminal_defaults_to_all_key_events_when_pynput_is_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(cfg, '_pynput_available', lambda: True)

    c = Cfg()

    assert c.keys.record_keys == RecordKeys.all
    assert c.keys.record_key_all_apps is False


def test_terminal_without_pynput_defaults_to_key_presses(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(cfg, '_pynput_available', lambda: False)

    c = Cfg()

    assert c.keys.record_keys == RecordKeys.press
    assert c.keys.record_key_all_apps is False


def test_terminal_without_pynput_rejects_all_key_events(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(cfg, '_pynput_available', lambda: False)

    with pytest.raises(ValidationError, match='record_keys cannot be all'):
        Cfg(record_keys=RecordKeys.all)
