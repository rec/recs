import typing as t

import recs
import recs.ui.splitter
from recs.audio import device
from recs.audio.device import InputDevice
from recs.audio.prefix_dict import PrefixDict

CHANNEL_SPLITTER = ':'
Strs = t.Sequence[t.Sequence[str]]
DeviceDict = PrefixDict[InputDevice]
Match = str | t.Sequence[str]


class ExcludeInclude:
    def __init__(self, exclude: Match = (), include: Match = ()) -> None:
        self.exclude = _Split(exclude)
        self.include = _Split(include)
        self.ed, self.id = self.exclude.devices, self.include.devices
        self.ec, self.ic = self.exclude.channels, self.include.channels

    def __call__(self, d: InputDevice, c: str = '') -> bool:
        if d.name in self.ed or (self.id and d.name not in self.id):
            return False
        if not c:
            return True
        if (d.name, c) in self.ec:
            return False
        return not self.ic or (d.name, c) in self.ic


class _Split:
    def __init__(self, matches: Match) -> None:
        self.devices: set[str] = set()
        self.channels: set[tuple[str, str]] = set()

        if not isinstance(matches, str):
            mat = matches
        else:
            mat = recs.ui.splitter.split(matches)

        bad_match: list[str] = []
        for m in mat:
            d, _, rest = m.partition(':')
            if not (dev := device.input_devices().get_value(d)):
                print('one', d)
                bad_match.append(m)
            elif not rest:
                self.devices.add(dev.name)
            else:
                ch, _, rest = rest.partition(':')
                if rest:
                    print('two', d)
                    bad_match.append(m)
                else:
                    self.channels.add((dev.name, ch))

        if bad_match:
            raise ValueError(f'{bad_match=}')
