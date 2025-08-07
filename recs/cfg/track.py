from recs.base import RecsError

from . import hash_cmp
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
            raise ValueError('Channels must be numbers')

        if channels[0] <= 0:
            raise ValueError('Channels must be positive')

        if len(channels) > 1 and channels[0] + 1 != channels[1]:
            raise ValueError('Channels must be in order')

        if channels[-1] > max_channels:
            s = "" if max_channels == 1 else "s"
            raise ValueError(f'Device has only {max_channels} channel{s}')

        return channels

    except ValueError as e:
        msg = f'{e.args[0]}: device={device_name}, channel={channel}'
        raise RecsError(msg) from None
