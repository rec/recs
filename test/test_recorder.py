import pytest

from recs.misc import RecsError
from recs.ui.recorder import Recorder


def test_recorder_fails(set_recs):
    with pytest.raises(RecsError) as e:
        Recorder({}, sleep_time=0.01)
    assert e.value.args == ('No devices or channels selected',)
