import typing as t

from recs.base.prefix_dict import PrefixDict

from .device import InputDevice, InputDevices
from .track import Track

CHANNEL_SPLITTER = '+'


class Aliases(PrefixDict[Track]):
    def __init__(self, aliases: t.Sequence[str], devices: InputDevices) -> None:
        super().__init__()

        assert devices
        self.devices = devices

        if not aliases:
            self.inv = {}
            return

        def split(name: str) -> tuple[str, str]:
            alias, sep, value = (n.strip() for n in name.partition('='))
            return alias, (value or alias)

        names, values = zip(*(split(n) for n in aliases))
        if len(set(names)) < len(names):
            raise ValueError(f'Duplicate aliases: {aliases}')

        self.update(sorted(zip(names, self.split_all(values))))

        inv: dict[Track, list[str]] = {}
        for k, v in self.items():
            inv.setdefault(v, []).append(k)

        if duplicate_aliases := [(k, v) for k, v in inv.items() if len(v) > 1]:
            raise ValueError(f'Duplicate alias values: {duplicate_aliases}')

        self.inv = {k: v[0] for k, v in sorted(inv.items())}

    def split_all(self, names: t.Iterable[str]) -> t.Sequence[Track]:
        bad_track_names = []
        result: list[Track] = []

        for name in names:
            try:
                result.append(self._to_track(name))
            except Exception:
                bad_track_names.append(name)

        if bad_track_names:
            s = 's' * (len(bad_track_names) != 1)
            raise ValueError(f'Bad device name{s}: {", ".join(bad_track_names)}')

        return result

    def display_name(self, x: InputDevice | Track) -> str:
        if isinstance(x, InputDevice):
            return self.inv.get(Track(x), x.name)
        else:
            return self.inv.get(x, x.channels_name)

    def _to_track(self, s: str) -> Track:
        try:
            return self[s]
        except KeyError:
            pass

        name, _, channels = (i.strip() for i in s.partition(CHANNEL_SPLITTER))
        try:
            track = self[name]
        except KeyError:
            device = self.devices[name]
        else:
            if track.channels:
                raise KeyError(f'Alias {name} is a device alias: "{s}" is not legal')
            device = track.device

        return Track(device, channels)
