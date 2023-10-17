from recs.ui.aliases import Aliases
from recs.ui.device_tracks import device_tracks
from recs.ui.track import Track

EMPTY = {
    'Ext': (Track(name='Ext', channel='1-2'),),
    'Flower 8': (
        Track(name='Flower 8', channel='1-2'),
        Track(name='Flower 8', channel='3-4'),
        Track(name='Flower 8', channel='5-6'),
        Track(name='Flower 8', channel='7-8'),
        Track(name='Flower 8', channel='9-10'),
    ),
    'Mic': (Track(name='Mic', channel='1'),),
}
SPLIT = {
    'Ext': (Track(name='Ext', channel='1-2'),),
    'Flower 8': (
        Track(name='Flower 8', channel='1'),
        Track(name='Flower 8', channel='2'),
        Track(name='Flower 8', channel='3-4'),
        Track(name='Flower 8', channel='5-6'),
        Track(name='Flower 8', channel='7-8'),
        Track(name='Flower 8', channel='9-10'),
    ),
    'Mic': (Track(name='Mic', channel='1'),),
}


def test_empty_device_tracks(mock_devices):
    dt = device_tracks(())
    assert dt == EMPTY


def test_device_tracks(mock_devices):
    aliases = Aliases(('e', 'Main = fl + 1', 'mai=Mic'))
    dt = device_tracks(aliases.values())
    import pprint

    pprint.pprint(dt)
    assert dt == SPLIT
