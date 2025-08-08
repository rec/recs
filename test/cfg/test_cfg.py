from pathlib import Path
from test.conftest import DEVICES_FILE

import pytest

from recs.base import RecsError
from recs.cfg import Cfg


def test_sdtype(mock_devices):
    Cfg(formats=['wav'], subtype='pcm_16', sdtype='int32')


def test_bad_devices(mock_devices):
    with pytest.raises(RecsError) as e:
        Cfg(devices=Path('unknown.json'))

    assert e.value.args == ('unknown.json does not exist',)


def test_devices(mock_devices):
    cfg = Cfg(devices=DEVICES_FILE)
    assert cfg.devices
