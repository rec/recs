import pytest

from recs import cfg
from recs.misc.to_time import to_time


def test_to_time():
    assert to_time('0') == 0
    assert to_time('00:00') == 0
    assert to_time('00:00:00') == 0
    assert to_time('1:00:00') == 3600
    assert to_time('1:00') == 60
    assert to_time('1') == 1
    assert to_time('9999') == 9999
    assert to_time('9999.125') == 9999.125
    assert to_time('60:00') == 3600
    assert to_time('2:05:23.5') == 7523.5


@pytest.mark.parametrize(
    'bad', ('-2', 'a', ':12', '1:60', '-1:59', '0:60:00', '-2:00:00')
)
def test_errors(bad):
    with pytest.raises(cfg.RecsError, match='--longest-file-time'):
        to_time(bad)