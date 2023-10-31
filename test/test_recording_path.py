import pytest

from recs.audio.track import Track
from recs.cfg import Subdirectory
from recs.misc.aliases import Aliases
from recs.misc.recording_path import recording_path

_channel, _device, _time = Subdirectory.channel, Subdirectory.device, Subdirectory.time

CHOICES: tuple[tuple[Subdirectory, ...]] = (
    ((), 'Ext + 3 + 20231015-164921'),
    #
    ((_channel,), '3/Ext + 20231015-164921'),
    ((_device,), 'Ext/3 + 20231015-164921'),
    ((_time,), '2023/10/15/Ext + 3 + 164921'),
    #
    ((_channel, _device), '3/Ext/20231015-164921'),
    ((_channel, _time), '3/2023/10/15/Ext + 164921'),
    ((_device, _channel), 'Ext/3/20231015-164921'),
    ((_device, _time), 'Ext/2023/10/15/3 + 164921'),
    ((_time, _channel), '2023/10/15/3/Ext + 164921'),
    ((_time, _device), '2023/10/15/Ext/3 + 164921'),
    #
    ((_channel, _device, _time), '3/Ext/2023/10/15/164921'),
    ((_channel, _time, _device), '3/2023/10/15/Ext/164921'),
    ((_device, _channel, _time), 'Ext/3/2023/10/15/164921'),
    ((_device, _time, _channel), 'Ext/2023/10/15/3/164921'),
    ((_time, _channel, _device), '2023/10/15/3/Ext/164921'),
    ((_time, _device, _channel), '2023/10/15/Ext/3/164921'),
)


@pytest.mark.parametrize('subs, expected', CHOICES)
def test_recording_path(subs, expected, mock_devices):
    path, filename = recording_path(Track('e', '3'), Aliases(), subs)
    actual = str(path / filename)
    assert actual == expected
