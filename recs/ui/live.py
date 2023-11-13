import contextlib
import dataclasses as dc
import time
import typing as t
from functools import cached_property

from humanfriendly import format_size
from rich import live
from rich.console import Console
from rich.table import Table

from ..base import to_time
from .table import TableFormatter, _to_str

RowsFunction = t.Callable[[], t.Iterator[dict[str, t.Any]]]

CONSOLE = Console(color_system='truecolor')


@dc.dataclass
class Live:
    rows: RowsFunction
    silent: bool = True
    retain: bool = False
    ui_refresh_rate: float = 10
    _last_update_time: float = 0

    def update(self) -> None:
        if not self.silent:
            t = time.time()
            if (t - self._last_update_time) >= 1 / self.ui_refresh_rate:
                self._last_update_time = t
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
    #    return contextlib.nullcontext() if self.silent else self.live

    @contextlib.contextmanager
    def context(self) -> t.Generator:
        if self.silent:
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

    if s < 0.001:
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
    s = to_time.to_str(x)
    return f'{s:>11}'


def _naturalsize(x: int) -> str:
    return f'{format_size(x):>9}' if x else ''


def _channel(x: str) -> str:
    return f' {x} ' if len(x) == 1 else x


TABLE_FORMATTER = TableFormatter(
    time=_time_to_str,
    device=None,
    channel=_channel,
    on=_on,
    recorded=_time_to_str,
    file_size=_naturalsize,
    file_count=str,
    volume=_volume,
)
