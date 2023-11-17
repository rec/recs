from recs.audio import device
from recs.audio.track import Track
from recs.base.aliases import Aliases
from recs.ui.device_tracks import device_track, device_tracks


def _device_tracks(*a, **ka):
    d = device_tracks(*a, **ka, devices=device.input_devices())
    return {k.name.split()[0].lower(): v for k, v in d.items()}


def test_empty__device_tracks(mock_devices):
    actual = _device_tracks(Aliases())
    expected = {
        'ext': [
            Track('ext', '1-2'),
            Track('ext', '3'),
        ],
        'flower': [
            Track('flower', '1-2'),
            Track('flower', '3-4'),
            Track('flower', '5-6'),
            Track('flower', '7-8'),
            Track('flower', '9-10'),
        ],
        'mic': [Track('mic', '1')],
    }
    assert actual == expected


def test_device_tracks_inc(mock_devices):
    aliases = 'e', 'Main = fl + 1', 'mai=Mic'
    actual = _device_tracks(Aliases(aliases), include=['Main'])
    expected = {
        'flower': [Track('flower', '1')],
    }
    assert actual == expected


def test_device_tracks_exc(mock_devices):
    aliases = 'x = e', 'Main = fl + 1', 'mai=Mic'
    actual = _device_tracks(Aliases(aliases), exclude=('x', 'Main'))
    expected = {
        'flower': [
            Track('flower', '2'),
            Track('flower', '3-4'),
            Track('flower', '5-6'),
            Track('flower', '7-8'),
            Track('flower', '9-10'),
        ],
        'mic': [Track('mic', '1')],
    }
    assert actual == expected


def test_device_tracks_inc_exc(mock_devices):
    aliases = 'e', 'Main = fl + 1', 'mai=Mic'
    actual = _device_tracks(Aliases(aliases), include=['e'], exclude=['e + 2'])
    expected = {
        'ext': [
            Track('ext', '1'),
            Track('ext', '3'),
        ],
    }
    assert actual == expected


def test_device_tracks_inc_exc2(mock_devices):
    aliases = 'e', 'Main = fl + 1', 'mai=Mic'
    actual = _device_tracks(Aliases(aliases), include=['e+1', 'e + 2-3'])
    expected = {
        'ext': [
            Track('ext', '1'),
            Track('ext', '2-3'),
        ],
    }
    assert actual == expected


def test_device_track_inc(mock_devices):
    aliases = Aliases(('x = e', 'Main = fl + 1', 'mai=Mic'))
    exc = aliases.split_all(('x', 'Main'))

    track = Track('mic', '1')
    actual = list(device_track(track.device, exc=exc))
    expected = [track]
    assert actual == expected
