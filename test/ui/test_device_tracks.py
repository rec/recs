from recs.cfg import Cfg
from recs.ui.device_tracks import device_track, device_tracks


def _device_tracks(alias=(), exclude=(), include=()):
    cfg = Cfg(alias=alias, exclude=exclude, include=include)
    d = device_tracks(cfg)
    actual = {k.name.split()[0].lower(): v for k, v in d}
    return actual, cfg.aliases.to_track


def test_empty__device_tracks(mock_devices):
    actual, to_track = _device_tracks()
    expected = {
        'ext': [
            to_track('ext + 1-2'),
            to_track('ext + 3'),
        ],
        'flower': [
            to_track('flower + 1-2'),
            to_track('flower + 3-4'),
            to_track('flower + 5-6'),
            to_track('flower + 7-8'),
            to_track('flower + 9-10'),
        ],
        'mic': [to_track('mic + 1')],
    }
    assert actual == expected


def test_device_tracks_inc(mock_devices):
    aliases = 'e', 'Main = fl + 1', 'mai=Mic'
    actual, to_track = _device_tracks(aliases, include=['Main'])
    expected = {
        'flower': [to_track('flower + 1')],
    }
    assert actual == expected


def test_device_tracks_exc(mock_devices):
    aliases = 'x = e', 'Main = fl + 1', 'mai=Mic'
    actual, to_track = _device_tracks(aliases, exclude=('x', 'Main'))
    expected = {
        'flower': [
            to_track('flower + 2'),
            to_track('flower + 3-4'),
            to_track('flower + 5-6'),
            to_track('flower + 7-8'),
            to_track('flower + 9-10'),
        ],
        'mic': [to_track('mic + 1')],
    }
    assert actual == expected


def test_device_tracks_inc_exc(mock_devices):
    aliases = 'e', 'Main = fl + 1', 'mai=Mic'
    actual, to_track = _device_tracks(aliases, include=['e'], exclude=['e + 2'])
    expected = {
        'ext': [
            to_track('ext + 1'),
            to_track('ext + 3'),
        ],
    }
    assert actual == expected


def test_device_tracks_inc_exc2(mock_devices):
    aliases = 'e', 'Main = fl + 1', 'mai=Mic'
    actual, to_track = _device_tracks(aliases, include=['e+1', 'e + 2-3'])
    expected = {
        'ext': [
            to_track('ext + 1'),
            to_track('ext + 2-3'),
        ],
    }
    assert actual == expected


def test_device_track_inc(mock_devices):
    cfg = Cfg(alias=('x = e', 'Main = fl + 1', 'mai=Mic'))
    exc = cfg.aliases.to_tracks(('x', 'Main'))

    track = cfg.aliases.to_track('mic + 1')
    actual = list(device_track(track.source, exc=exc))
    expected = [track]
    assert actual == expected
