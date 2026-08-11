import numbers
from collections.abc import Iterator, Mapping
from typing import Any

from rich.table import Table


def to_str(x: Any) -> str:
    if isinstance(x, str):
        return x

    assert isinstance(x, numbers.Real), str(x)
    return f'{x:6.1%}'


class TableFormatter:
    def __init__(self, **kwargs: Any):
        self.kwargs = kwargs

    def _to_str(self, row: Mapping[str, Any], column: str) -> str:
        _to_str = self.kwargs.get(column) or to_str
        if (x := row.get(column)) is not None:
            return _to_str(x)
        return ''

    def __call__(self, rows: Iterator[Mapping[str, Any]]) -> Table:
        t = Table(*self.kwargs)
        cols = set(self.kwargs)
        for r in rows:
            if unknown := set(r) - cols:  # pragma: no cover
                raise ValueError(f'{unknown=}')
            t.add_row(*(self._to_str(r, c) for c in self.kwargs))
        return t
