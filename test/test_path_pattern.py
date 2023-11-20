from recs.cfg import Cfg, PathPattern
from recs.cfg.path_pattern import Req as R

from .conftest import TIME, TIMESTAMP


def test_empty(mock_devices):
    pp = PathPattern('')
    assert pp.unused == tuple(R)
    assert pp.name_parts == pp.pstring_parts == ()
    assert pp.times(TIME) == {
        'day': '15',
        'hour': '16',
        'minute': '49',
        'month': '10',
        'second': '21',
        'year': '2023',
    }
    assert pp.path == '{track} + {year}{month}{day}_{hour}{minute}{second}'

    cfg = Cfg()
    actual = pp.evaluate(
        track=cfg.aliases.to_track('Ext + 1'),
        aliases=cfg.aliases,
        timestamp=TIMESTAMP,
        index=1,
    )
    expected = 'Ext + 1 + 20231015_164921'
    assert actual == expected


def test_simple(mock_devices):
    pp = PathPattern('{time}/{date}')
    assert pp.unused == (R.device, R.channel)
    assert pp.name_parts == ()
    assert pp.pstring_parts == ('date', 'time')
    assert pp.times(TIME) == {'date': '20231015', 'time': '164921'}
    assert pp.path == '{time}/{date}/{track}'

    cfg = Cfg()
    actual = pp.evaluate(
        track=cfg.aliases.to_track('Ext + 1'),
        aliases=cfg.aliases,
        timestamp=TIMESTAMP,
        index=1,
    )
    expected = '164921/20231015/Ext + 1'
    assert actual == expected


def test_mix(mock_devices):
    pp = PathPattern('{device}/%Y/%m')
    assert pp.unused == (R.channel, R.day, R.hour, R.minute, R.second)
    assert pp.name_parts == ('device',)
    assert pp.pstring_parts == ()
    assert pp.times(TIME) == {'day': '15', 'hour': '16', 'minute': '49', 'second': '21'}
    assert pp.path == '{device}/%Y/%m/{channel} + {day}_{hour}{minute}{second}'

    cfg = Cfg()
    actual = pp.evaluate(
        track=cfg.aliases.to_track('Ext + 1'),
        aliases=cfg.aliases,
        timestamp=TIMESTAMP,
        index=1,
    )
    expected = 'Ext/2023/10/1 + 15_164921'
    assert actual == expected


def test_index(mock_devices):
    pp = PathPattern('recording/{track}/{index}')
    cfg = Cfg()
    actual = pp.evaluate(
        track=cfg.aliases.to_track('Ext + 1'),
        aliases=cfg.aliases,
        timestamp=TIMESTAMP,
        index=1,
    )
    expected = 'recording/Ext + 1/1'
    assert actual == expected
