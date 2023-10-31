import pytest

from recs.misc import RecsError
from recs.recs import Recs
from recs.ui.recorder import Recorder


def test_recorder_fails():
    with pytest.raises(RecsError) as e:
        Recorder(Recs(), {})
    assert e.value.args == ('No devices or channels selected',)
