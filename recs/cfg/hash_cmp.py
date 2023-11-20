import typing as t
from abc import ABC
from functools import total_ordering


@total_ordering
class HashCmp(ABC):
    _key: t.Any

    def __eq__(self, o: t.Any) -> bool:
        return isinstance(o, type(self)) and self._key == o._key

    def __lt__(self, o) -> bool:
        if not isinstance(o, type(self)):
            return NotImplemented
        return self._key < o._key

    def __hash__(self) -> int:
        return hash(self._key)
