import contextlib
import time
import typing as t

from rich.table import Table

from recs.audio import device

from .. import RecsError
from .device_recorder import DeviceRecorder
from .session import Session
from .table import TableFormatter


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

    @contextlib.contextmanager
    def context(self) -> t.Generator:
        try:
            with contextlib.ExitStack() as stack:
                for d in self.device_recorders:
                    stack.enter_context(d.input_stream)
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
