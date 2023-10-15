import typing as t
from functools import cached_property

from recs.audio.prefix_dict import PrefixDict

from .track import Track, split_all


class Aliases(PrefixDict[Track]):
    def __init__(self, aliases: t.Sequence[str]) -> None:
        if not aliases:
            super().__init__()
            return

        def split(name: str) -> tuple[str, str]:
            alias, sep, value = (n.strip() for n in name.partition('='))
            return alias, (value or alias)

        al, values = zip(*(split(n) for n in aliases))
        if len(set(al)) < len(al):
            raise ValueError(f'Duplicates in alias names: {aliases}')

        super().__init__(sorted(zip(al, split_all(values))))

    @cached_property
    def inv(self) -> dict[Track, str]:
        d: dict = {}
        for k, v in self.items():
            d.setdefault(v, []).append(k)

        if duplicate_aliases := [(k, v) for k, v in d.items() if len(v) > 1]:
            raise ValueError(f'{duplicate_aliases = }')

        return {k: v[0] for k, v in sorted(d.items())}
