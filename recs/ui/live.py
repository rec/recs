import contextlib
import dataclasses as dc
import typing as t
from functools import cached_property

import humanize
from rich import live
from rich.console import Console
from rich.table import Table

from recs.misc import to_time

from .table import TableFormatter, _to_str

RowsFunction = t.Callable[[], t.Iterator[dict[str, t.Any]]]

CONSOLE = Console(color_system='truecolor')


@dc.dataclass
class Live:
    rows: RowsFunction
    quiet: bool = True
    retain: bool = False
    ui_refresh_rate: float = 23

    def update(self) -> None:
        if not self.quiet:
            self.live.update(self.table())

    @cached_property
    def live(self) -> live.Live:
        return live.Live(
            self.table(),
            console=CONSOLE,
            refresh_per_second=self.ui_refresh_rate,
            transient=not self.retain,
        )

    def table(self) -> Table:
        return TABLE_FORMATTER(self.rows())

    # def context(self) -> t.Generator:
    #    return contextlib.nullcontext() if self.quiet else self.live

    @contextlib.contextmanager
    def context(self) -> t.Generator:
        if self.quiet:
            yield
        else:
            with self.live:
                yield


def _rgb(r=0, g=0, b=0) -> str:
    r, g, b = (int(i) % 256 for i in (r, g, b))
    return f'[rgb({r},{g},{b})]'


def _on(active: bool) -> str:
    if active:
        return _rgb(g=0xFF) + '•'
    return ''


def _volume(x) -> str:
    try:
        s = sum(x) / len(x)
    except Exception:
        s = x

    if not s:
        return ''

    if s < 1 / 3:
        r = 0
        g = 3 * s
    else:
        r = (3 * s - 1) / 2
        g = 1 - r

    return _rgb(r * 256, g * 256) + _to_str(x)


def _time_to_str(x) -> str:
    if not x:
        return ''
    return to_time.to_str(x)


def _naturalsize(x: int) -> str:
    if not x:
        return ''
    return humanize.naturalsize(x)


TABLE_FORMATTER = TableFormatter(
    time=_time_to_str,
    device=None,
    channel=None,
    on=_on,
    recorded=_time_to_str,
    file_size=_naturalsize,
    volume=_volume,
)
