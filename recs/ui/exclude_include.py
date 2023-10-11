import typing as t

from recs.audio import device
from recs.audio.device import InputDevice

CHANNEL_SPLITTER = '+'


class ExcludeInclude:
    def __init__(
        self, exclude: t.Sequence[str] = (), include: t.Sequence[str] = ()
    ) -> None:
        self.exclude = set(split_all(exclude))
        self.include = set(split_all(include))

    def __call__(self, d: InputDevice, c: str = '') -> bool:
        if (d.name, c) in self.exclude:
            return False

        if (d.name, c) in self.include:
            return True

        if not c:
            return not self.include or any(n == d.name for n, _ in self.include)

        if (d.name, '') in self.exclude:
            return False

        if (d.name, '') in self.include:
            return True

        return not self.include


def split_all(it: t.Sequence[str]) -> t.Iterator[tuple[str, str]]:
    def split(s: str) -> tuple[str, InputDevice | None, str]:
        name, _, channels = (i.strip() for i in s.partition(CHANNEL_SPLITTER))
        return name, device.input_devices().get_value(name), channels

    splits = [split(i) for i in it]
    if bad_devices := [n for n, d, _ in splits if d is None]:
        raise ValueError(f'{bad_devices=}')

    yield from ((d.name, channels) for _, d, channels in splits if d)
