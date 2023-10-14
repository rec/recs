import contextlib
import time
import typing as t
from functools import cached_property

from rich.console import Console
from rich.live import Live
from rich.table import Table

from recs.audio import device

from .. import RecsError
from .device_recorder import DeviceRecorder
from .session import Session
from .table import TableFormatter

CONSOLE = Console(color_system='truecolor')


class Recorder:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.start_time = time.time()
        values = device.input_devices().values()
        dr1 = (d for d in values if session.exclude_include(d))
        dr2 = (DeviceRecorder(d, session) for d in dr1)
        self.device_recorders = tuple(d for d in dr2 if d)

        if not self.device_recorders:
            raise RecsError('No devices or channels selected!')

    @property
    def elapsed_time(self) -> float:
        return time.time() - self.start_time

    def table(self) -> Table:
        return TABLE_FORMATTER(self.rows())

    def rows(self) -> t.Iterator[dict[str, t.Any]]:
        yield {'time': f'{self.elapsed_time:9.3f}'}
        for v in self.device_recorders:
            yield from v.rows()

    def update(self) -> None:
        if not self.session.recs.quiet:
            self.live.update(self.table())

    @cached_property
    def live(self) -> Live:
        assert not self.session.recs.quiet
        return Live(
            self.table(),
            console=CONSOLE,
            refresh_per_second=self.session.recs.ui_refresh_rate,
            transient=not self.session.recs.retain,
        )

    @contextlib.contextmanager
    def context(self) -> t.Generator:
        try:
            with contextlib.ExitStack() as stack:
                for d in self.device_recorders:
                    stack.enter_context(d.input_stream)
                if not self.session.recs.quiet:
                    stack.enter_context(self.live)
                yield
        finally:
            self.stop()

    def stop(self) -> None:
        for d in self.device_recorders:
            d.stop()


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
    block=_to_str,
    rms=None,
    rms_mean=None,
    amplitude=None,
    amplitude_mean=None,
)
