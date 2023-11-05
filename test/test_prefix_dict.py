import pytest

from recs.audio.device import InputDevice
from recs.base.prefix_dict import PrefixDict

InputDevices = PrefixDict[InputDevice]


def _inp(name, max_input_channels=1, default_samplerate=44_100) -> InputDevice:
    return InputDevice(info=dict(locals()))


NAMES = 'One', 'ONE', 'Oner', 'Two', 'Three', 'FOUR'
DEVICES = InputDevices({n: _inp(n) for n in NAMES})


@pytest.mark.parametrize('name', NAMES + ('tw', 'f'))
def test_match(name):
    DEVICES[name]


@pytest.mark.parametrize('name', ('one', 'x', 't', 'T', ''))
def test_fail(name):
    with pytest.raises(KeyError):
        DEVICES[name]
