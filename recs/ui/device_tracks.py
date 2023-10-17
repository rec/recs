import itertools
import typing as t

from recs.audio import device

from .track import Track


def device_tracks(aliases: t.Iterator[Track]) -> dict[str, tuple[Track, ...]]:
    def channels(d: device.InputDevice) -> t.Iterator[Track]:
        next_free_channel = 1

        def dc(*channels) -> Track:
            return Track(d.name, '-'.join(str(i) for i in channels))

        def unaliased_channels(limit: int) -> t.Iterator[Track]:
            # Automatically generated stereo pairs can only look like 1-2, 5-7, not 2-3
            if odd := next_free_channel < limit and not (next_free_channel % 2):
                yield dc(next_free_channel)

            it = iter(range(next_free_channel + odd, limit + 1))
            while channels := tuple(itertools.islice(it, 2)):
                yield dc(*channels)

        for dch in aliases:
            if dch.name == d.name and dch.channel:
                a, _, b = dch.channel.partition('-')
                yield from unaliased_channels(int(a) - 1)
                yield dch
                next_free_channel = int(b or a) + 1

        yield from unaliased_channels(d.channels)

    return {d.name: tuple(channels(d)) for d in device.input_devices().values()}
