import contextlib
import dataclasses as dc
import typing as t
from functools import cached_property

from rich import live
from rich.console import Console
from rich.table import Table

from .table import TableFormatter

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

    @contextlib.contextmanager
    def context(self) -> t.Generator:
        if self.quiet:
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
