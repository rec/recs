import typing as t

from recs.audio.prefix_dict import PrefixDict

from .track import Track

CHANNEL_SPLITTER = '+'


class Aliases(PrefixDict[Track]):
    def __init__(self, aliases: t.Sequence[str] = ()) -> None:
        super().__init__()
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

    def to_track(self, s: str) -> Track:
        try:
            return self[s]
        except KeyError:
            pass

        name, _, channels = (i.strip() for i in s.partition(CHANNEL_SPLITTER))
        try:
            track = self[name]
        except KeyError:
            pass
        else:
            if track.channels:
                raise KeyError(f'Alias {name} is a device alias: {s} is not legal')
            name = track.name

        return Track(name, channels)

    def split_all(self, names: t.Iterable[str]) -> t.Sequence[Track]:
        bad_device_names = []
        result: list[Track] = []

        for name in names:
            try:
                result.append(self.to_track(name))
            except Exception:
                bad_device_names.append(name)

        if bad_device_names:
            s = 's' * (len(bad_device_names) != 1)
            raise ValueError(f'Bad device name{s}: {", ".join(bad_device_names)}')

        return result
