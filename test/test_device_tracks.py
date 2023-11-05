from recs.audio.track import Track
from recs.base.aliases import Aliases
from recs.ui.device_tracks import device_track, device_tracks

from .conftest import EXT, FLOWER, MIC


def test_empty_device_tracks(mock_devices):
    actual = device_tracks(Aliases())
    expected = {
        EXT: [
            Track(EXT, '1-2'),
            Track(EXT, '3'),
        ],
        FLOWER: [
            Track(FLOWER, '1-2'),
            Track(FLOWER, '3-4'),
            Track(FLOWER, '5-6'),
            Track(FLOWER, '7-8'),
            Track(FLOWER, '9-10'),
        ],
        MIC: [Track(MIC, '1')],
    }
    assert actual == expected


def test_device_tracks_inc(mock_devices):
    aliases = 'e', 'Main = fl + 1', 'mai=Mic'
    actual = device_tracks(Aliases(aliases), include=['Main'])
    expected = {
        FLOWER: [Track(FLOWER, '1')],
    }
    assert actual == expected


def test_device_tracks_exc(mock_devices):
    aliases = 'x = e', 'Main = fl + 1', 'mai=Mic'
    actual = device_tracks(Aliases(aliases), exclude=('x', 'Main'))
    expected = {
        FLOWER: [
            Track(FLOWER, '2'),
            Track(FLOWER, '3-4'),
            Track(FLOWER, '5-6'),
            Track(FLOWER, '7-8'),
            Track(FLOWER, '9-10'),
        ],
        MIC: [Track(MIC, '1')],
    }
    assert actual == expected


def test_device_tracks_inc_exc(mock_devices):
    aliases = 'e', 'Main = fl + 1', 'mai=Mic'
    actual = device_tracks(Aliases(aliases), include=['e'], exclude=['e + 2'])
    expected = {
        EXT: [
            Track(EXT, '1'),
            Track(EXT, '3'),
        ],
    }
    assert actual == expected


def test_device_tracks_inc_exc2(mock_devices):
    aliases = 'e', 'Main = fl + 1', 'mai=Mic'
    actual = device_tracks(Aliases(aliases), include=['e+1', 'e + 2-3'])
    expected = {
        EXT: [
            Track(EXT, '1'),
            Track(EXT, '2-3'),
        ],
    }
    assert actual == expected


def test_device_track_inc(mock_devices):
    aliases = Aliases(('x = e', 'Main = fl + 1', 'mai=Mic'))
    exc = aliases.split_all(('x', 'Main'))
    actual = list(device_track(MIC, exc=exc))
    expected = [Track(MIC, '1')]
    assert actual == expected
