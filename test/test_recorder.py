import pytest

from recs.base import RecsError
from recs.cfg import Cfg
from recs.ui.recorder import Recorder


def test_recorder_fails(mock_devices):
    with pytest.raises(RecsError) as e:
        Recorder(Cfg(include=['e'], exclude=['e']))
    assert e.value.args == ('No devices or channels selected',)
