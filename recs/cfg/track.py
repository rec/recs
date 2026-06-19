import typing as t

from recs.base import RecsError

from . import hash_cmp
from .device import InputDevice
from .source import Source

__all__ = ('Track',)


class Track(hash_cmp.HashCmp):
    name: str

    def __init__(self, source: Source, channel: str | tuple[int, ...] = ()) -> None:
        self.source = source

        channels = channel or ()
        if isinstance(channels, str):
            self.channels = _channels(channels, source.name, source.channels)
        else:
            self.channels = channels

        self._key = source.name, self.channels

        if self.channels:
            a, b = self.channels[0], self.channels[-1]
            self.slice = slice(a - 1, b)
            self.name = f'{a}' if a == b else f'{a}-{b}'

        else:
            self.slice = slice(0)
            self.name = ''

    def __str__(self) -> str:
        if self.channels:
            return f'{self.source.name} + {self.name}'
        return self.source.name

    def __repr__(self) -> str:
        return f"Track('{self}')"


def _channels(channel: str, device_name: str, max_channels: int) -> tuple[int, ...]:
    try:
        split = channel.split('-')
        if not (1 <= len(split) <= 2):
            raise ValueError('Only mono or stereo are supported')

        try:
            channels = tuple(int(i) for i in split)
        except ValueError:
            raise ValueError('Channels must be numbers') from None

        if channels[0] <= 0:
            raise ValueError('Channels must be positive')

        if len(channels) > 1 and channels[0] + 1 != channels[1]:
            raise ValueError('Channels must be in order')

        if channels[-1] > max_channels:
            s = '' if max_channels == 1 else 's'
            raise ValueError(f'Device has only {max_channels} channel{s}')

        return channels

    except ValueError as e:
        msg = f'{e.args[0]}: device={device_name}, channel={channel}'
        raise RecsError(msg) from None


def source_track(
    d: InputDevice, exc: t.Sequence[Track] = (), inc: t.Sequence[Track] = ()
) -> t.Iterator[Track]:
    if Track(d) in exc:
        return

    excs = [i for i in exc if d.name == i.source.name]
    incs = [i for i in inc if d.name == i.source.name]
    if inc and not incs:
        return

    tracks = [i for i in incs if i.channels]

    ic = {int(c) for t in tracks for c in t.channels} or set(range(1, d.channels + 1))
    ec = {int(c) for t in excs for c in t.channels}

    channels = sorted(ic - ec)

    def track_channel() -> int:
        return tracks[0].channels[-1]

    while channels:
        if tracks:
            found = False
            while channels and track_channel() >= channels[0]:
                channels.pop(0)
                found = True

            if found:
                yield tracks.pop(0)
                continue

            if not channels:
                break

        c1 = channels.pop(0)
        ch = f'{c1}'
        if (
            channels
            and channels[0] == c1 + 1
            and c1 % 2
            and not (tracks and track_channel() == c1 + 1)
        ):
            c2 = channels.pop(0)
            assert c1 + 1 == c2
            ch = f'{c1}-{c2}'

        yield Track(d, ch)

    yield from tracks
