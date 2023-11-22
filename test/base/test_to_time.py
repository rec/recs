import pytest

from recs.base.times import to_str, to_time

BAD = '-2', 'a', ':12', '1:60', '-1:59', '0:60:00', '-2:00:00', '', '0:0:0:0'
GOOD = (
    ('0', 0),
    ('00:00', 0),
    ('00:00:00', 0),
    ('1:00:00', 3600),
    ('1:00', 60),
    ('1', 1),
    ('9999', 9999),
    ('9999.125', 9999.125),
    ('60:00', 3600),
    ('2:05:23.5', 7523.5),
)


@pytest.mark.parametrize('str, value', GOOD)
def test_to_time(str, value):
    assert to_time(str) == value
    assert to_time(to_str(value)) == value


@pytest.mark.parametrize('bad', BAD)
def test_errors(bad):
    with pytest.raises(ValueError):
        to_time(bad)
