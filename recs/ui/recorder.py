import contextlib
import time
import typing as t

from rich.table import Table
from threa import Runnable

from recs import RECS
from recs.audio import device
from recs.misc import RecsError

from . import live
from .device_tracks import device_tracks

InputDevice = device.InputDevice
TableMaker = t.Callable[[], Table]


class Recorder(Runnable):
    def __init__(self) -> None:
        from .device_recorder import DeviceRecorder

        super().__init__()

        self.start_time = time.time()
        self.live = live.Live(self.rows)

        dts = device_tracks(RECS.aliases, RECS.exclude, RECS.include).items()
        self.device_recorders = tuple(DeviceRecorder(k, self, v) for k, v in dts)

        if not self.device_recorders:
            raise RecsError('No devices or channels selected')

        self.start()

    def run(self) -> None:
        self.start()
        with self.context():
            while self.running:
                time.sleep(RECS.sleep_time)
                self.live.update()

    @property
    def elapsed_time(self) -> float:
        return time.time() - self.start_time

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
                stack.enter_context(self.live.context())
                yield
        finally:
            self.stop()

    def on_stopped(self) -> None:
        if self.running and all(d.stopped for d in self.device_recorders):
            self.stop()

    def stop(self) -> None:
        self.running.clear()
        for d in self.device_recorders:
            d.stop()
        self.stopped.set()
