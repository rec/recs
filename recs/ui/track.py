import dataclasses as dc
from functools import cached_property

from recs import RecsError
from recs.audio import device

__all__ = ('Track',)


@dc.dataclass(frozen=True, order=True)
class Track:
    name: str
    channel: str = ''

    def __post_init__(self) -> None:
        self.__dict__['name'] = self.device.name
        self.channels

    @cached_property
    def device(self) -> device.InputDevice:
        try:
            return device.input_devices()[self.name.strip()]
        except KeyError:
            raise RecsError(f'Bad device name {self.name=}') from None

    @cached_property
    def slice(self) -> slice:
        c1, *c2 = self.channels
        return slice(c1 - 1, c1 + bool(c2))

    @cached_property
    def channels(self) -> tuple[int, ...]:
        if not self.channel:
            return ()

        try:
            try:
                channels = tuple(int(i) for i in self.channel.split('-'))
            except Exception:
                raise ValueError('Channels must be numbers')

            if len(channels) == 2:
                if (channels[0] + 1) != channels[1]:
                    raise ValueError('Channels must be in order')

            if not (1 <= len(channels) <= 2):
                raise ValueError('Only mono or stereo are supported')

            if channels[0] <= 0:
                raise ValueError('Channels must be positive')

            if channels[-1] > self.device.channels:
                raise ValueError(f'Device has only {self.device.channels} channels')

        except ValueError as e:
            msg = f'{e.args[0]}: device={self.name}, {self.channel=}'
            raise RecsError(msg) from None

        return channels

    replace = dc.replace
