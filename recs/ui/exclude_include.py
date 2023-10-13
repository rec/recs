import dataclasses as dc
import typing as t

from recs.audio import device
from recs.audio.device import InputDevice

CHANNEL_SPLITTER = '+'


@dc.dataclass(frozen=True, order=True, slots=True)
class Track:
    name: str
    channel: str = ''

    @property
    def without_channel(self) -> 'Track':
        return dc.replace(self, channel='')


class ExcludeInclude:
    def __init__(
        self, exclude: t.Sequence[str] = (), include: t.Sequence[str] = ()
    ) -> None:
        self.exclude = set(split_all(exclude))
        self.include = set(split_all(include))

    def match(self, dc: Track):
        if dc in self.exclude:
            return False

        if dc in self.include:
            return True

        if not dc.channel:
            return not self.include or any(i.name == dc.name for i in self.include)

        if dc.without_channel in self.exclude:
            return False

        if dc.without_channel in self.include:
            return True

        return not self.include

    def __call__(self, d: InputDevice, c: str = '') -> bool:
        return self.match(Track(d.name, c))


def split_all(it: t.Sequence[str]) -> t.Iterator[Track]:
    def split(s: str) -> tuple[str, str, str]:
        name, _, channels = (i.strip() for i in s.partition(CHANNEL_SPLITTER))
        try:
            full_name = device.input_devices()[name].name
        except KeyError:
            full_name = ''
        return name, full_name, channels

    splits = [split(i) for i in it]
    if bad_devices := [n for n, f, _ in splits if not f]:
        raise ValueError(f'{bad_devices=}')

    yield from (Track(d, channels) for _, d, channels in splits)
