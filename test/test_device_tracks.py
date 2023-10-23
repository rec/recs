from recs.ui.aliases import Aliases
from recs.ui.device_tracks import device_track, device_tracks
from recs.ui.track import Track


def test_empty_device_tracks(mock_devices):
    actual = device_tracks(Aliases())
    expected = {
        'Ext': [Track('Ext', '1-2')],
        'Flower 8': [
            Track('Flower 8', '1-2'),
            Track('Flower 8', '3-4'),
            Track('Flower 8', '5-6'),
            Track('Flower 8', '7-8'),
            Track('Flower 8', '9-10'),
        ],
        'Mic': [Track('Mic', '1')],
    }
    assert actual == expected


def test_device_tracks_inc(mock_devices):
    aliases = 'e', 'Main = fl + 1', 'mai=Mic'
    actual = device_tracks(Aliases(aliases), include=['Main'])
    expected = {'Flower 8': [Track('Flower 8', '1')]}
    assert actual == expected


def test_device_tracks_exc(mock_devices):
    aliases = 'x = e', 'Main = fl + 1', 'mai=Mic'
    actual = device_tracks(Aliases(aliases), exclude=('x', 'Main'))
    expected = {
        'Flower 8': [
            Track('Flower 8', '2'),
            Track('Flower 8', '3-4'),
            Track('Flower 8', '5-6'),
            Track('Flower 8', '7-8'),
            Track('Flower 8', '9-10'),
        ],
        'Mic': [Track('Mic', '1')],
    }
    assert actual == expected


def test_device_track_inc(mock_devices):
    aliases = Aliases(('x = e', 'Main = fl + 1', 'mai=Mic'))
    exc = aliases.split_all(('x', 'Main'))
    device = input_devices()['Mic']
    actual = list(device_track(device, exc=exc))
    expected = [Track('Mic', '1')]
    assert actual == expected
