from recs.audio.device import input_devices
from recs.ui.aliases import Aliases
from recs.ui.device_tracks import device_track, device_tracks
from recs.ui.track import Track


def test_empty_device_tracks(mock_devices):
    actual = sorted(device_tracks())
    expected = [
        Track(name='Ext', channel='1-2'),
        Track(name='Flower 8', channel='1-2'),
        Track(name='Flower 8', channel='3-4'),
        Track(name='Flower 8', channel='5-6'),
        Track(name='Flower 8', channel='7-8'),
        Track(name='Flower 8', channel='9-10'),
        Track(name='Mic', channel='1'),
    ]
    assert actual == expected


def test_device_tracks(mock_devices):
    aliases = 'e', 'Main = fl + 1', 'mai=Mic'
    actual = sorted(device_tracks(aliases))

    expected = [
        Track(name='Ext', channel='1-2'),
        Track(name='Flower 8', channel='1-2'),
        Track(name='Flower 8', channel='3-4'),
        Track(name='Flower 8', channel='5-6'),
        Track(name='Flower 8', channel='7-8'),
        Track(name='Flower 8', channel='9-10'),
        Track(name='Mic', channel='1'),
    ]
    assert actual == expected


def test_device_tracks_inc(mock_devices):
    aliases = 'e', 'Main = fl + 1', 'mai=Mic'
    actual = sorted(device_tracks(aliases, include=['Main']))
    expected = [Track(name='Flower 8', channel='1')]
    assert actual == expected


def test_device_tracks_exc(mock_devices):
    aliases = 'x = e', 'Main = fl + 1', 'mai=Mic'
    actual = sorted(device_tracks(aliases, exclude=('x', 'Main')))
    expected = [
        Track(name='Flower 8', channel='2'),
        Track(name='Flower 8', channel='3-4'),
        Track(name='Flower 8', channel='5-6'),
        Track(name='Flower 8', channel='7-8'),
        Track(name='Flower 8', channel='9-10'),
        Track(name='Mic', channel='1'),
    ]
    assert actual == expected


def test_device_track_inc(mock_devices):
    aliases = Aliases(('x = e', 'Main = fl + 1', 'mai=Mic'))
    exc = aliases.split_all(('x', 'Main'))
    device = input_devices()['Mic']
    actual = sorted(device_track(device, exc=exc))
    expected = [Track(name='Mic', channel='1')]
    assert actual == expected
