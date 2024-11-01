from test.conftest import TIME, TIMESTAMP

import pytest

from recs.base import RecsError
from recs.cfg import Cfg
from recs.cfg.path_pattern import PathPattern


def test_empty(mock_devices):
    pp = PathPattern('')
    assert pp.name_parts == pp.pstring_parts == ()
    assert pp.times(TIME) == {
        'day': '15',
        'hour': '16',
        'minute': '49',
        'month': '10',
        'second': '21',
        'year': '2023',
    }
    assert pp.path == '{track} + {year}{month}{day}-{hour}{minute}{second}'

    cfg = Cfg()
    actual = pp.make_path(
        track=cfg.aliases.to_track('Ext + 1'),
        aliases=cfg.aliases,
        timestamp=TIMESTAMP,
        index=1,
    )
    expected = 'Ext + 1 + 20231015-164921'
    assert str(actual) == expected


def test_simple(mock_devices):
    pp = PathPattern('{time}/{date}')
    assert pp.name_parts == ()
    assert pp.pstring_parts == ('date', 'time')
    assert pp.times(TIME) == {'date': '20231015', 'time': '164921'}
    assert pp.path == '{time}/{date}/{track}'

    cfg = Cfg()
    actual = pp.make_path(
        track=cfg.aliases.to_track('Ext + 1'),
        aliases=cfg.aliases,
        timestamp=TIMESTAMP,
        index=1,
    )
    expected = '164921/20231015/Ext + 1'
    assert str(actual) == pp.unix_to_windows_path(expected)


def test_mix(mock_devices):
    pp = PathPattern('{device}/%Y/%m')
    assert pp.name_parts == ('device',)
    assert pp.pstring_parts == ()
    assert pp.times(TIME) == {'day': '15', 'hour': '16', 'minute': '49', 'second': '21'}
    assert pp.path == '{device}/%Y/%m/{channel} + {day}-{hour}{minute}{second}'

    cfg = Cfg()
    actual = pp.make_path(
        track=cfg.aliases.to_track('Ext + 1'),
        aliases=cfg.aliases,
        timestamp=TIMESTAMP,
        index=1,
    )
    expected = 'Ext/2023/10/1 + 15-164921'
    assert str(actual) == pp.unix_to_windows_path(expected)


def test_index(mock_devices):
    pp = PathPattern('recording/{track}/{index}')
    cfg = Cfg()
    actual = pp.make_path(
        track=cfg.aliases.to_track('Ext + 1'),
        aliases=cfg.aliases,
        timestamp=TIMESTAMP,
        index=1,
    )
    expected = 'recording/Ext + 1/1'
    assert str(actual) == pp.unix_to_windows_path(expected)


def test_bad_field(mock_devices):
    with pytest.raises(RecsError) as e:
        PathPattern('recording/{truck}/{index}')

    assert e.value.args == ('Unknown: truck',)


def test_bad_month(mock_devices):
    with pytest.raises(RecsError) as e:
        PathPattern('{year}{day}')

    assert e.value.args == ('Must specify year or day with month: {year}{day}',)


def test_bad_minute(mock_devices):
    with pytest.raises(RecsError) as e:
        PathPattern('{minute}')

    assert e.value.args == ('Must specify hour or second with minute: {minute}',)
