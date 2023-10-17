import pytest

from recs.ui.aliases import Aliases
from recs.ui.track import Track


def test_empty_aliases():
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
