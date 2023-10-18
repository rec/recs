import pytest

from recs.ui.track import Track

OK = 'flow', 'f', 'e', 'f + 9-10', 'f + 8', 'f + 8-9'
ERRORS = 'flaw', 'a', 'f + a', 'f + 0', 'f + 1-3', 'f + 3-2', 'f + 11', 'f + 1-2-3'


@pytest.mark.parametrize('desc', OK)
def test_track(desc, mock_devices):
    Track(*desc.split('+'))


@pytest.mark.parametrize('desc', ERRORS)
def test_track_fails(desc, mock_devices):
    with pytest.raises(ValueError):
        Track(*desc.split('+'))


def test_split_all(mock_devices):
    assert list(Track.split_all([])) == []
    assert list(Track.split_all(['flow'])) == [Track('Flower 8')]
    assert list(Track.split_all(['flow + 1-2'])) == [Track('Flower 8', '1-2')]

    actual = list(Track.split_all(['flow + 1-2', 'flow + 3', 'ext']))
    expected = [Track('Flower 8', '1-2'), Track('Flower 8', '3'), Track('Ext')]
    assert actual == expected

    with pytest.raises(ValueError) as e:
        list(Track.split_all((['flow + 1-2', 'flow + 3', 'ext', 'oxt'])))

    assert e.value.args[0] == 'Bad device name: oxt'
