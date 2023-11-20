from recs.cfg import PathPattern
from recs.cfg.path_pattern import Required as R

from .conftest import TIME


def test_empty():
    pp = PathPattern('')
    assert pp.fields == tuple(R)
    assert pp.name_parts == pp.pstring_parts == ()
    assert pp.times(TIME) == {}


def test_simple():
    pp = PathPattern('{time}/{date}')
    assert pp.fields == (R.device, R.channel)
    assert pp.name_parts == ()
    assert pp.pstring_parts == ('time', 'date')
    assert pp.times(TIME) == {'date': '20231015', 'time': '164921'}


def test_mix():
    pp = PathPattern('{device}/%Y/%m')
    assert pp.fields == (R.channel, R.day, R.hour, R.minute, R.second)
    assert pp.name_parts == ('device',)
    assert pp.pstring_parts == ()
    assert pp.times(TIME) == {}
