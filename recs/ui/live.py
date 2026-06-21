import os
import sys
import typing as t
from functools import cached_property

from rich import live
from rich.console import Console
from rich.table import Table
from threa import Runnable

from recs.cfg import Cfg

from . import presentation

CONSOLE = Console(color_system='truecolor')
CURSES_TERMS: tuple[str, ...] = (
    'ansi',
    'linux',
    'screen',
    'screen-256color',
    'tmux',
    'tmux-256color',
    'vt100',
    'xterm',
    'xterm-256color',
    'xterm-color',
)


class Live(Runnable):
    _last_update_time: float = 0
    needs_update_thread = True
    closed = False

    def __init__(
        self, rows: t.Callable[[], t.Iterator[t.Mapping[str, t.Any]]], cfg: Cfg
    ) -> None:
        self.rows = rows
        self.cfg = cfg
        term = os.environ.get('TERM', '')
        self.enabled: bool = (
            not cfg.console.silent
            and CONSOLE.is_terminal
            and term.lower() in CURSES_TERMS
        )
        if not cfg.console.silent and not self.enabled:
            print(
                f'WARNING: Terminal does not support the live display (TERM={term!r})',
                file=sys.stderr,
            )
            self.enabled = False
        super().__init__()

    def update(self) -> None:
        if self.enabled:
            self.live.update(self.table())

    @cached_property
    def live(self) -> live.Live:
        return live.Live(
            self.table(),
            console=CONSOLE,
            refresh_per_second=self.cfg.console.ui_refresh_rate,
            transient=self.cfg.console.clear_terminal,
        )

    def table(self) -> Table:
        table = Table(*presentation.COLUMNS)
        view = presentation.view_model(self.rows())
        for row in view.rows:
            table.add_row(*(_rich_text(cell) for cell in row.cells))
        return table

    def start(self) -> None:
        super().start()
        if self.enabled:
            self.live.start(refresh=True)

    def stop(self) -> None:
        if self.enabled:
            self.live.stop()
        super().stop()


def _rgb(r: int = 0, g: int = 0, b: int = 0) -> str:
    r, g, b = (int(i) % 256 for i in (r, g, b))
    return f'[rgb({r},{g},{b})]'


def _rich_text(cell: presentation.Cell) -> str:
    if cell.style == 'active':
        return _rgb(g=0xFF) + cell.text
    if cell.style == 'offline':
        return _rgb(r=0xFF) + cell.text
    if cell.style == 'volume-low':
        return _rgb(g=0xFF) + cell.text
    if cell.style == 'volume-high':
        return _rgb(r=0xFF) + cell.text
    return cell.text
