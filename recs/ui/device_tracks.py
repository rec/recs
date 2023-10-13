import itertools
import typing as t

from recs.audio import device
from recs.ui.exclude_include import Track


def device_tracks(aliases: t.Iterator[Track]) -> dict[str, tuple[Track, ...]]:
    def channels(d: device.InputDevice) -> t.Iterator[Track]:
        last = 0

        def dc(*channels) -> Track:
            return Track(d.name, '-'.join(str(i) for i in channels))

        def unaliased_channels(limit: int) -> t.Iterator[Track]:
            c = last + 1
            if c < limit and last % 2:
                yield dc(c)
                c += 1

            it = iter(range(c, limit))
            while channels := tuple(itertools.islice(it, 2)):
                yield dc(*channels)

        for dch in aliases:
            if dch.name == d.name and dch.channel:
                a, _, b = dch.channel.partition('-')
                yield from unaliased_channels(int(a))
                yield dch
                last = int(b or a)

        yield from unaliased_channels(d.channels)

    return {d.name: tuple(channels(d)) for d in device.input_devices().values()}
