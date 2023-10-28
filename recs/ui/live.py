import contextlib
import typing as t
from functools import cached_property

from rich import live
from rich.console import Console
from rich.table import Table

from recs import RECS

from .table import TableFormatter

RowsFunction = t.Callable[[], t.Iterator[dict[str, t.Any]]]

CONSOLE = Console(color_system='truecolor')


class Live:
    def __init__(self, rows: RowsFunction):
        self.rows = rows

    def update(self) -> None:
        if not RECS.quiet:
            self.live.update(self.table())

    @cached_property
    def live(self) -> live.Live:
        return live.Live(
            self.table(),
            console=CONSOLE,
            refresh_per_second=RECS.ui_refresh_rate,
            transient=not RECS.retain,
        )

    def table(self) -> Table:
        return TABLE_FORMATTER(self.rows())

    @contextlib.contextmanager
    def context(self) -> t.Generator:
        if RECS.quiet:
            yield
        else:
            with self.live:
                yield


def _to_str(x: str | float) -> str:
    if isinstance(x, str):
        return x

    global RED, GREEN, BLUE
    RED = (RED + 1) % 256
    GREEN = (GREEN + 1) % 256
    BLUE = (BLUE + 1) % 256
    return f'[rgb({RED},{GREEN},{BLUE})]{x:>7,}'


RED = 256 // 3
GREEN = 512 // 3
BLUE = 0


TABLE_FORMATTER = TableFormatter(
    time=None,
    device=None,
    channel=None,
    count=_to_str,
    rms=None,
    rms_mean=None,
    volume=None,
    volume_mean=None,
)
