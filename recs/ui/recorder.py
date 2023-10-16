import contextlib
import time
import typing as t
from functools import cached_property

from rich.console import Console
from rich.live import Live
from rich.table import Table
from threa import Runnable

from recs.audio import device

from .. import RecsError
from .device_recorder import DeviceRecorder
from .session import Session
from .table import TableFormatter

CONSOLE = Console(color_system='truecolor')


class Recorder(Runnable):
    def __init__(self, session: Session) -> None:
        super().__init__()

        self.session = session
        self.start_time = time.time()

        devices = device.input_devices().values()
        ie_devices = (d for d in devices if session.exclude_include(d))
        recorders = (dr for d in ie_devices if (dr := DeviceRecorder(d, session)))
        self.device_recorders = tuple(recorders)

        if not self.device_recorders:
            raise RecsError('No devices or channels selected!')

        for d in self.device_recorders:
            d.stopped.on_set.append(self._on_stopped)

        self.start()

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

    def _on_stopped(self):
        if self.running and all(d.stopped for d in self.device_recorders):
            self.stop()

    def stop(self) -> None:
        self.running.clear()
        for d in self.device_recorders:
            d.stop()
        self.stopped.set()


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
