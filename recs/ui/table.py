import numbers
import typing as t

from rich.table import Table


def to_str(x: t.Any) -> str:
    if isinstance(x, str):
        return x

    assert isinstance(x, numbers.Real), str(x)
    return f'{x:6.1%}'


class TableFormatter:
    def __init__(self, **kwargs: t.Any):
        self.kwargs = kwargs

    def _to_str(self, row, column) -> str:
        _to_str = self.kwargs.get(column) or to_str
        if (x := row.get(column)) is not None:
            return _to_str(x)
        return ''

    def __call__(self, rows: t.Iterator[dict[str, t.Any]]) -> Table:
        t = Table(*self.kwargs)
        cols = set(self.kwargs)
        for r in rows:
            if unknown := set(r) - cols:  # pragma: no cover
                raise ValueError(f'{unknown=}')
            t.add_row(*(self._to_str(r, c) for c in self.kwargs))
        return t
