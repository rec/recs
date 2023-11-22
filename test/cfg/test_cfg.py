from pathlib import Path
from test.conftest import DEVICES_FILE

import pytest

from recs.base import RecsError
from recs.cfg import Cfg


def test_sdtype(mock_devices):
    Cfg(format='wav', subtype='pcm_16', sdtype='int32')


def test_bad_format(mock_devices):
    Cfg(format='wav')
    with pytest.raises(RecsError) as e:
        Cfg(format='wov')

    assert e.value.args == ('Cannot understand --format="wov"',)


def test_bad_devices(mock_devices):
    with pytest.raises(RecsError) as e:
        Cfg(devices=Path('unknown.json'))

    assert e.value.args == ('unknown.json does not exist',)


def test_devices(mock_devices):
    cfg = Cfg(devices=DEVICES_FILE)
    assert cfg.devices


def test_time_error(mock_devices):
    Cfg(longest_file_time='0:00:00')
    with pytest.raises(RecsError) as e:
        Cfg(longest_file_time='0:00:00:00')

    assert e.value.args == ('Do not understand --longest-file-time=0:00:00:00',)

    Cfg(shortest_file_time='0:59')
    with pytest.raises(RecsError) as e:
        Cfg(shortest_file_time='0:60')

    assert e.value.args == ('Do not understand --shortest-file-time=0:60',)
