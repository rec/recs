from abc import ABC
from functools import total_ordering
from typing import Any


@total_ordering
class HashCmp(ABC):
    _key: Any

    def __eq__(self, o: Any) -> bool:
        return isinstance(o, type(self)) and self._key == o._key

    def __lt__(self, o: Any) -> bool:
        if not isinstance(o, type(self)):
            return NotImplemented
        return bool(self._key < o._key)

    def __hash__(self) -> int:
        return hash(self._key)
