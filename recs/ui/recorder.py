import contextlib
import typing as t

from rich.table import Table
from threa import HasThread, Runnable

from recs.base import RecsError, times
from recs.cfg import device, Cfg

from . import live
from .device_recorder import DeviceRecorder
from .device_tracks import device_tracks

InputDevice = device.InputDevice
TableMaker = t.Callable[[], Table]


class Recorder(Runnable):
    processes: dict[InputDevice, DeviceProcess | None]

    def __init__(self, cfg: Cfg) -> None:
        super().__init__()

        self.device_tracks = device_tracks(cfg)
        if not self.device_tracks:
            raise RecsError('No devices or channels selected')

        self.cfg = cfg
        self.live = live.Live(self.rows, cfg)
        self.start_time = times.time()

        tracks = self.device_tracks.values()

        self.live_thread = HasThread(self._live_thread)
        self.processes = {d: None for d in tracks}

    def run(self) -> None:
        self.start()
        self.live_thread.start()
        try:
            with contextlib.ExitStack() as stack:
                for d in self.device_recorders:
                    stack.enter_context(d)
                stack.enter_context(self.live)

                while self.running:
                    times.sleep(self.cfg.sleep_time)
        finally:
            self.stop()

    @property
    def elapsed_time(self) -> float:
        return times.time() - self.start_time

    def rows(self) -> t.Iterator[dict[str, t.Any]]:
        yield {
            'time': self.elapsed_time,
            'recorded': self.recorded_time,
            'file_size': self.file_size,
            'file_count': self.file_count,
        }
        for v in self.device_recorders:
            yield from v.rows()

    @property
    def file_count(self) -> int:
        return sum(d.file_count for d in self.device_recorders)

    @property
    def file_size(self) -> int:
        return sum(d.file_size for d in self.device_recorders)

    @property
    def recorded_time(self) -> float:
        return sum(d.recorded_time for d in self.device_recorders)

    def on_stopped(self) -> None:
        if self.running and all(d.stopped for d in self.device_recorders):
            self.stop()

    def stop(self) -> None:
        self.running.clear()
        self.live_thread.stop()
        for d in self.device_recorders:
            d.stop()
        self.stopped.set()

    def _live_thread(self):
        while self.running:
            times.sleep(self.cfg.sleep_time)
            self.live.update()

    def _process_thread(self):
        t = times.time()
        while self.running:
            pass
