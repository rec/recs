from pathlib import Path
from test.conftest import DEVICES_FILE

import pytest
from pydantic import ValidationError

from recs.cfg import Cfg


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
