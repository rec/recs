import contextlib
import time
import typing as t

from rich.table import Table
from threa import Runnable

from recs.audio import device
from recs.misc import RecsError
from recs.recs import Recs
from recs.ui.device_tracks import DeviceTracks

from . import live

InputDevice = device.InputDevice
TableMaker = t.Callable[[], Table]


class Recorder(Runnable):
    def __init__(self, recs: Recs, device_tracks: DeviceTracks) -> None:
        from .device_recorder import DeviceRecorder

        super().__init__()
        self.recs = recs

        self.start_time = time.time()
        self.live = live.Live(
            self.rows,
            quiet=recs.quiet,
            retain=recs.retain,
            ui_refresh_rate=recs.ui_refresh_rate,
        )

        drs = (DeviceRecorder(k, self, v) for k, v in device_tracks.items())
        self.device_recorders = tuple(drs)

        if not self.device_recorders:
            raise RecsError('No devices or channels selected')

    def run(self) -> None:
        self.start()
        with self.context():
            while self.running:
                time.sleep(self.recs.sleep_time)
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
