import pytest

from recs.cfg import Cfg


def _Aliases(*aliases):
    return Cfg(alias=aliases).aliases


def test_empty_aliases(mock_devices):
    aliases = _Aliases()
    assert not aliases.tracks
    assert not aliases.inv


def test_aliases(mock_devices):
    aliases = _Aliases('e', 'Main = fl + 7-8', 'mai=Mic')
    to_track = aliases.to_track

    assert aliases
    assert aliases.inv
    assert sorted(aliases.inv) == sorted(aliases.tracks.values())

    assert aliases.tracks['E'] == to_track('Ext')
    assert aliases.tracks['Main'] == to_track('Flower 8 + 7-8')
    assert aliases.tracks['mai'] == to_track('Mic')
    assert aliases.tracks['Mai'] == to_track('Mic')
    with pytest.raises(KeyError):
        aliases.tracks['X']
    with pytest.raises(KeyError):
        aliases.tracks['m']


def test_errors(mock_devices):
    with pytest.raises(ValueError) as e:
        _Aliases('e', 'e = fl + 7-8', 'mai=M')
    assert 'Duplicate aliases:' in e.value.args[0]

    with pytest.raises(ValueError) as e:
        _Aliases('e', 'Main = fl + 7-8', 'mai=fl + 7-8')
    assert 'Duplicate alias values:' in e.value.args[0]


def test_to_tracks(mock_devices):
    aliases = _Aliases()
    to_tracks = aliases.to_tracks
    to_track = aliases.to_track

    assert list(to_tracks([])) == []
    assert list(to_tracks(['flow'])) == [to_track('Flower 8')]
    assert list(to_tracks(['flow + 1-2'])) == [to_track('Flower 8 + 1-2')]

    actual = list(to_tracks(['flow + 1-2', 'flow + 3', 'ext']))
    expected = [to_track('Flower 8 + 1-2'), to_track('Flower 8 + 3'), to_track('Ext')]
    assert actual == expected

    with pytest.raises(ValueError) as e:
        list(to_tracks((['flow + 1-2', 'flow + 3', 'ext', 'oxt'])))

    assert e.value.args[0] == 'Bad device name: oxt'


def test_error(mock_devices):
    aliases = _Aliases('e', 'Main = fl + 7-8', 'mai=Mic')
    aliases.to_track('Main')
    with pytest.raises(KeyError) as e:
        aliases.to_track('Main + 3')
    assert e.value.args == ('Alias Main is a device alias: "Main + 3" is not legal',)


def test_to_track(mock_devices):
    aliases = _Aliases('e', 'Main = fl + 1', 'mai=Mic')
    aliases.to_track('e + 2-3')
