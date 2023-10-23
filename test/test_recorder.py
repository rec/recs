import pytest

from recs import RECS, RecsError
from recs.ui.recorder import Recorder


def test_recorder_fails(monkeypatch):
    monkeypatch.setattr(RECS, 'include', ['flow'])
    monkeypatch.setattr(RECS, 'exclude', ['flow'])
    with pytest.raises(RecsError) as e:
        Recorder()
    assert e.value.args == ('No devices or channels selected',)
