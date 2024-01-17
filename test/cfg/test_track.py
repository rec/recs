import pytest

from recs.cfg import Cfg

OK = 'flow', 'f', 'e', 'f + 9-10', 'f + 8', 'f + 8-9'
KEY_ERRORS = 'flaw', 'a'
VALUE_ERRORS = 'f + a', 'f + 0', 'f + 1-3', 'f + 3-2', 'f + 11', 'f + 1-2-3'


@pytest.mark.parametrize('desc', OK)
def test_track(desc, mock_devices):
    to_track = Cfg().aliases.to_track
    to_track(desc)


@pytest.mark.parametrize('desc', KEY_ERRORS)
def test_track_fails_key(desc, mock_devices):
    to_track = Cfg().aliases.to_track
    with pytest.raises(KeyError):
        to_track(desc)


@pytest.mark.parametrize('desc', VALUE_ERRORS)
def test_track_fails_value(desc, mock_devices):
    to_track = Cfg().aliases.to_track
    with pytest.raises(ValueError):
        to_track(desc)


def test_track_display(mock_devices):
    t = Cfg().aliases.to_track('flow')
    assert str(t) == 'Flower 8'
    assert repr(t) == "Track('Flower 8')"

    t = Cfg().aliases.to_track('flow + 2-3')
    assert str(t) == 'Flower 8 + 2-3'
    assert repr(t) == "Track('Flower 8 + 2-3')"
