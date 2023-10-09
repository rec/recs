import typing as t

import recs
from recs import split
from recs.audio import device
from recs.audio.prefix_dict import PrefixDict

CHANNEL_SPLITTER = ':'
Strs = t.Sequence[t.Sequence[str]]
DeviceDict = PrefixDict[device.InputDevice]
Match = str | t.Sequence[str]


class ExcludeInclude:
    def __init__(self, exclude: Match = (), include: Match = ()) -> None:
        self.exclude = _Accept(exclude)
        self.include = _Accept(include)

    def __call__(self, *args) -> bool:
        return not self.exclude(*args) and (not self.include or self.include(*args))


class _Accept(list):
    def __init__(self, matches: Match) -> None:
        if not matches:
            super().__init__()
            return

        def dev(i) -> tuple:
            k, *a = split(i, CHANNEL_SPLITTER)
            try:
                return device.input_devices()[k], *a
            except KeyError:
                return k, *a

        if isinstance(matches, str):
            s = matches
        else:
            s = recs.PART_SPLITTER.join(matches)

        super().__init__(dev(i) for i in (s and split(s)))

        if unknown_devices := [k for k, *_ in self if isinstance(k, str)]:
            raise ValueError(f'{unknown_devices=}')

        if too_many_colons := [m for m in self if len(m) > 2]:
            raise ValueError(f'{too_many_colons=}')

    def __call__(self, *args) -> bool:
        assert 1 <= len(args) <= 2
        # TODO: this is gnarly, find a better way
        return any(args == i[:len(args)] for i in self)
