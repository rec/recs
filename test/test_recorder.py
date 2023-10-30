import pytest

from recs.misc import RecsError
from recs.ui.recorder import Recorder


def test_recorder_fails(set_recs):
    set_recs(include=['flow'], exclude=['flow'])
    with pytest.raises(RecsError) as e:
        Recorder()
    assert e.value.args == ('No devices or channels selected',)
