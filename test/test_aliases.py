import pytest

from recs.audio.track import Track
from recs.base.aliases import Aliases


def test_empty_aliases(mock_devices):
    aliases = Aliases(())
    assert not aliases
    assert not aliases.inv


def test_aliases(mock_devices):
    aliases = Aliases(('e', 'Main = fl + 7-8', 'mai=Mic'))
    assert aliases
    assert aliases.inv
    assert sorted(aliases.inv) == sorted(aliases.values())
    assert aliases['E'] == Track('Ext')
    assert aliases['Main'] == Track('Flower 8', '7-8')
    assert aliases['mai'] == Track('Mic')
    assert aliases['Mai'] == Track('Mic')
    with pytest.raises(KeyError):
        aliases['X']
    with pytest.raises(KeyError):
        aliases['m']


def test_errors(mock_devices):
    with pytest.raises(ValueError) as e:
        Aliases(('e', 'e = fl + 7-8', 'mai=M'))
    assert 'Duplicate aliases:' in e.value.args[0]

    with pytest.raises(ValueError) as e:
        Aliases(('e', 'Main = fl + 7-8', 'mai=fl + 7-8'))
    assert 'Duplicate alias values:' in e.value.args[0]


def test_split_all(mock_devices):
    split_all = Aliases(()).split_all

    assert list(split_all([])) == []
    assert list(split_all(['flow'])) == [Track('Flower 8')]
    assert list(split_all(['flow + 1-2'])) == [Track('Flower 8', '1-2')]

    actual = list(split_all(['flow + 1-2', 'flow + 3', 'ext']))
    expected = [Track('Flower 8', '1-2'), Track('Flower 8', '3'), Track('Ext')]
    assert actual == expected

    with pytest.raises(ValueError) as e:
        list(split_all((['flow + 1-2', 'flow + 3', 'ext', 'oxt'])))

    assert e.value.args[0] == 'Bad device name: oxt'


def test_error(mock_devices):
    aliases = Aliases(('e', 'Main = fl + 7-8', 'mai=Mic'))
    aliases._to_track('Main')
    with pytest.raises(KeyError) as e:
        aliases._to_track('Main + 3')
    assert e.value.args == ('Alias Main is a device alias: "Main + 3" is not legal',)


def test_to_track(mock_devices):
    aliases = Aliases(('e', 'Main = fl + 1', 'mai=Mic'))
    aliases._to_track('e + 2-3')
