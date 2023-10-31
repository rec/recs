import pytest

from recs.cfg import Cfg
from recs.misc import RecsError
from recs.ui.recorder import Recorder


def test_recorder_fails():
    with pytest.raises(RecsError) as e:
        Recorder(Cfg(), {})
    assert e.value.args == ('No devices or channels selected',)
