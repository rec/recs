import pytest

from recs.audio.device import InputDevice
from recs.audio.prefix_dict import PrefixDict

InputDevices = PrefixDict[InputDevice]

NAMES = 'One', 'ONE', 'Oner', 'Two', 'Three', 'FOUR'
DEVICES = InputDevices({n: InputDevice(info={'name': n}) for n in NAMES})


@pytest.mark.parametrize('name', NAMES + ('tw', 'f'))
def test_match(name):
    DEVICES[name]


@pytest.mark.parametrize('name', ('one', 'x', 't', 'T', ''))
def test_fail(name):
    with pytest.raises(KeyError):
        DEVICES[name]
