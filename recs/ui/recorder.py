import contextlib
import typing as t

from rich.table import Table
from threa import Runnable

from recs.base import RecsError, times
from recs.cfg import device

from ..cfg.cfg import Cfg
from . import live
from .device_recorder import DeviceRecorder
from .device_tracks import device_tracks

InputDevice = device.InputDevice
TableMaker = t.Callable[[], Table]


class Recorder(Runnable):
    def __init__(self, cfg: Cfg) -> None:
        super().__init__()
        self.cfg = cfg
        self.device_tracks = device_tracks(
            cfg.aliases, cfg.devices, cfg.exclude, cfg.include
        )
        if not self.device_tracks:
            raise RecsError('No devices or channels selected')

        self.start_time = times.time()
        self.live = live.Live(
            self.rows,
            silent=cfg.silent,
            retain=cfg.retain,
            ui_refresh_rate=cfg.ui_refresh_rate,
        )

        tracks = self.device_tracks.values()
        self.device_recorders = tuple(DeviceRecorder(cfg, t) for t in tracks)

        for d in self.device_recorders:
            d.stopped.on_set.append(self.on_stopped)

    def run(self) -> None:
        self.start()
        with self.context():
            while self.running:
                times.sleep(self.cfg.sleep_time)
                self.live.update()

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
