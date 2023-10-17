import typing as t

from recs.audio.prefix_dict import PrefixDict

from .track import Track


class Aliases(PrefixDict[Track]):
    def __init__(self, aliases: t.Sequence[str]) -> None:
        if not aliases:
            super().__init__()
            self.inv = {}
            return

        def split(name: str) -> tuple[str, str]:
            alias, sep, value = (n.strip() for n in name.partition('='))
            return alias, (value or alias)

        al, values = zip(*(split(n) for n in aliases))
        if len(set(al)) < len(al):
            raise ValueError(f'Duplicate aliases: {aliases}')

        super().__init__(sorted(zip(al, Track.split_all(values))))

        d: dict[Track, list[str]] = {}
        for k, v in self.items():
            d.setdefault(v, []).append(k)

        if duplicate_aliases := [(k, v) for k, v in d.items() if len(v) > 1]:
            raise ValueError(f'Duplicate alias values: {duplicate_aliases}')

        self.inv = {k: v[0] for k, v in sorted(d.items())}
