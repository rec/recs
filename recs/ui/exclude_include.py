import typing as t

from recs.audio.device import InputDevice
from recs.ui.track import Track


class ExcludeInclude:
    def __init__(
        self, exclude: t.Sequence[str] = (), include: t.Sequence[str] = ()
    ) -> None:
        self.exclude = set(Track.split_all(exclude))
        self.include = set(Track.split_all(include))

    def match(self, dc: Track):
        if dc in self.exclude:
            return False

        if dc in self.include:
            return True

        if not dc.channel:
            return not self.include or any(i.name == dc.name for i in self.include)

        if (dr := dc.replace(channel='')) in self.exclude:
            return False

        if dr in self.include:
            return True

        return not self.include

    def __call__(self, d: InputDevice, c: str = '') -> bool:
        return self.match(Track(d.name, c))
