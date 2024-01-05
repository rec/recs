import typing as t

from recs.base.prefix_dict import PrefixDict
from recs.base import prefix_dict, RecsError


from .device import InputDevice, InputDevices
from .track import Track

CHANNEL_SPLITTER = '+'


class Aliases:
    tracks: prefix_dict.PrefixDict[Track]

    def __init__(self, aliases: t.Sequence[str], devices: InputDevices) -> None:
        self.tracks = PrefixDict()

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
            raise RecsError(f'Duplicate aliases: {aliases}')

        self.tracks.update(sorted(zip(names, self.to_tracks(values))))

        inv: dict[Track, list[str]] = {}
        for k, v in self.tracks.items():
            inv.setdefault(v, []).append(k)

        if duplicate_aliases := [(k, v) for k, v in inv.items() if len(v) > 1]:
            raise RecsError(f'Duplicate alias values: {duplicate_aliases}')

        self.inv = {k: v[0] for k, v in sorted(inv.items())}

    def to_tracks(self, names: t.Iterable[str]) -> t.Sequence[Track]:
        errors: dict[str, list[str]] = {}
        result: list[Track] = []

        for name in names:
            try:
                result.append(self.to_track(name))
            except KeyError as e:
                key, error = e.args
                errors.setdefault(error, []).append(key)

        if not errors:
            return result

        def err(k, v) -> str:
            s = 's' * (len(v) != 1)
            return f'{k.capitalize()} device name{s}: {", ".join(v)}'

        devs = '", "'.join(sorted(self.devices))
        devices = f'Devices: "{devs}"'
        errs = (err(k, v) for k, v in errors.items())

        raise RecsError('\n'.join([*errs, devices]))

    def display_name(self, x: InputDevice | Track, short: bool = True) -> str:
        if isinstance(x, InputDevice):
            return self.inv.get(Track(x), x.name)

        default = x.name if short else str(x)
        return self.inv.get(x, default)

    def to_track(self, track_name: str) -> Track:
        try:
            return self.tracks[track_name]
        except KeyError:
            pass

        name, _, channels = (i.strip() for i in track_name.partition(CHANNEL_SPLITTER))
        try:
            track = self.tracks[name]
        except KeyError:
            device = self.devices[name]
        else:
            if track.channels:
                raise KeyError(track_name, 'impossible')
            device = track.device

        return Track(device, channels)
