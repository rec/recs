from functools import cached_property

from recs import RecsError
from recs.audio import device as _device
from recs.audio import hash_cmp

__all__ = ('Track',)


class Track(hash_cmp.HashCmp):
    def __init__(
        self, device: str | _device.InputDevice, channel: str | tuple[int, ...] = ()
    ) -> None:
        if isinstance(device, str):
            self.device = _device.input_devices()[device]
        else:
            self.device = device
        channels = channel or ()
        if isinstance(channels, str):
            self.channels = _channels(channels, self.device.name, self.device.channels)
        else:
            self.channels = channels

    def __str__(self) -> str:
        if self.channels:
            return f'{self.device.name}+{self.channels_name}'
        return self.device.name

    def __repr__(self) -> str:
        return f'Track({self})'

    @cached_property
    def slice(self) -> slice:
        c1, *c2 = self.channels
        return slice(c1 - 1, c1 + bool(c2))

    @cached_property
    def channels_name(self) -> str:
        return '-'.join(str(c) for c in self.channels)

    @cached_property
    def _key(self) -> tuple[str, tuple[int, ...]]:
        return self.device.name, self.channels


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
            raise ValueError(f'Device has only {max_channels} channels')

        return channels

    except ValueError as e:
        msg = f'{e.args[0]}: device={device_name}, channel={channel}'
        raise RecsError(msg) from None
