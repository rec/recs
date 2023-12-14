import typing as t
from functools import cached_property

from humanfriendly import format_size
from rich import live
from rich.console import Console
from rich.table import Table
from threa import Runnable

from recs.base import times
from recs.base.types import Active
from recs.cfg import Cfg

from .table import TableFormatter, to_str

RowsFunction = t.Callable[[], t.Iterator[dict[str, t.Any]]]

CONSOLE = Console(color_system='truecolor')


class Live(Runnable):
    _last_update_time: float = 0

    def __init__(self, rows: RowsFunction, cfg: Cfg) -> None:
        self.rows = rows
        self.cfg = cfg
        super().__init__()

    def update(self) -> None:
        if not self.cfg.silent:
            self.live.update(self.table())

    @cached_property
    def live(self) -> live.Live:
        return live.Live(
            self.table(),
            console=CONSOLE,
            refresh_per_second=self.cfg.ui_refresh_rate,
            transient=self.cfg.clear,
        )

    def table(self) -> Table:
        return TABLE_FORMATTER(self.rows())

    def start(self) -> None:
        super().start()
        if not self.cfg.silent:
            self.live.start(refresh=True)

    def stop(self) -> None:
        if not self.cfg.silent:
            self.live.stop()
        super().stop()


def _rgb(r=0, g=0, b=0) -> str:
    r, g, b = (int(i) % 256 for i in (r, g, b))
    return f'[rgb({r},{g},{b})]'


def _on(active: Active) -> str:
    if active == Active.active:
        return _rgb(g=0xFF) + '•'
    elif active == Active.offline:
        return _rgb(r=0xFF) + 'ˣ'
    else:
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

    return _rgb(r * 256, g * 256) + to_str(x)


def _time_to_str(x) -> str:
    if not x:
        return ''
    s = times.to_str(x)
    return f'{s:>11}'


def _naturalsize(x: int) -> str:
    if not x:
        return ''

    fs = format_size(x)

    # Fix #97
    value, _, unit = fs.partition(' ')
    if unit != 'bytes':
        integer, _, decimal = value.partition('.')
        decimal = (decimal + '00')[:2]
        fs = f'{integer}.{decimal} {unit}'

    return f'{fs:>9}'


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
