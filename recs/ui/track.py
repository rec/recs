import dataclasses as dc
import typing as t
from functools import cached_property

from recs.audio import device

__all__ = ('Track',)

CHANNEL_SPLITTER = '+'


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
            raise ValueError(f'Bad device name {self.name=}')

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
            raise ValueError(f'{e.args[0]}: device={self.name}, {self.channel=}')

        return channels

    replace = dc.replace

    @staticmethod
    def split_all(it: t.Sequence[str]) -> t.Sequence['Track']:
        bad_device_names = []
        result: list[Track] = []

        for s in it:
            name, _, channels = (i.strip() for i in s.partition(CHANNEL_SPLITTER))
            try:
                result.append(Track(name, channels))
            except Exception:
                bad_device_names.append(name)

        if bad_device_names:
            s = 's' * (len(bad_device_names) != 1)
            raise ValueError(f'Bad device name{s}: {", ".join(bad_device_names)}')

        return result
