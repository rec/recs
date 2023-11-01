import numbers
import typing as t

from rich.table import Table


def _to_str(x: t.Any) -> str:
    if isinstance(x, str):
        return x

    if isinstance(x, numbers.Real):
        return f'{x:6.1%}'

    try:
        len(x)
    except TypeError:  # pragma: no cover
        return str(x)

    assert len(x) <= 2, f'{len(x)}'
    return ' |'.join(_to_str(i) for i in x)


class TableFormatter:
    def __init__(self, **kwargs: t.Any):
        self.kwargs = kwargs

    def _to_str(self, row, column) -> str:
        to_str = self.kwargs.get(column) or _to_str
        if (x := row.get(column)) is not None:
            return to_str(x)
        return ''

    def __call__(self, rows: t.Iterator[dict[str, t.Any]]) -> Table:
        t = Table(*self.kwargs)
        cols = set(self.kwargs)
        for r in rows:
            if unknown := set(r) - cols:  # pragma: no cover
                raise ValueError(f'{unknown=}')
            t.add_row(*(self._to_str(r, c) for c in self.kwargs))
        return t
