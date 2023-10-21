import pytest

from recs.ui.track import Track

OK = 'flow', 'f', 'e', 'f + 9-10', 'f + 8', 'f + 8-9'
KEY_ERRORS = 'flaw', 'a'
VALUE_ERRORS = 'f + a', 'f + 0', 'f + 1-3', 'f + 3-2', 'f + 11', 'f + 1-2-3'


@pytest.mark.parametrize('desc', OK)
def test_track(desc, mock_devices):
    Track(*desc.split('+'))


@pytest.mark.parametrize('desc', KEY_ERRORS)
def test_track_fails_key(desc, mock_devices):
    with pytest.raises(KeyError):
        Track(*desc.split('+'))


@pytest.mark.parametrize('desc', VALUE_ERRORS)
def test_track_fails_value(desc, mock_devices):
    with pytest.raises(ValueError):
        Track(*desc.split('+'))
