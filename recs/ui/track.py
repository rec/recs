import dataclasses as dc
import typing as t

from recs.audio import device

__all__ = 'Track', 'split_all'

CHANNEL_SPLITTER = '+'


@dc.dataclass(frozen=True, order=True, slots=True)
class Track:
    name: str
    channel: str = ''

    @property
    def without_channel(self) -> 'Track':
        return dc.replace(self, channel='')


def split_all(it: t.Sequence[str]) -> t.Iterator[Track]:
    splits = [_split_one(i) for i in it]
    if bad_devices := [name for name, full_name, _ in splits if not full_name]:
        raise ValueError(f'{bad_devices=}')

    yield from (Track(full_name, channels) for _, full_name, channels in splits)


def _split_one(s: str) -> tuple[str, str, str]:
    name, _, channels = (i.strip() for i in s.partition(CHANNEL_SPLITTER))

    try:
        full_name = device.input_devices()[name].name
    except KeyError:
        full_name = ''

    return name, full_name, channels
