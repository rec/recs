import contextlib
import typing as t

from rich.table import Table
from threa import HasThread, Runnable

from recs.base import RecsError, times
from recs.cfg import Cfg, device

from . import live
from .device_recorder import DeviceRecorder
from .device_tracks import device_tracks
from .total_state import TotalState

InputDevice = device.InputDevice
TableMaker = t.Callable[[], Table]


class Recorder(Runnable):
    def __init__(self, cfg: Cfg) -> None:
        super().__init__()

        self.device_tracks = device_tracks(cfg)
        if not self.device_tracks:
            raise RecsError('No devices or channels selected')

        self.cfg = cfg
        self.live = live.Live(self.rows, cfg)

        tracks = self.device_tracks.values()

        self.total_state = TotalState(self.device_tracks)

        def make_recorder(t) -> DeviceRecorder:
            dr = DeviceRecorder(cfg, t, self.stop, self.total_state.update)
            dr.stopped.on_set.append(self.on_stopped)
            return dr

        self.device_recorders = tuple(make_recorder(t) for t in tracks)
        self.device_thread = HasThread(self.check_devices, looping=True)
        self.devices = device.input_names()
        self.live_thread = HasThread(self.update_live, looping=True)

    def run(self) -> None:
        self.start()
        try:
            with contextlib.ExitStack() as stack:
                for d in self.device_recorders:
                    stack.enter_context(d)
                stack.enter_context(self.live)

                while self.running:
                    times.sleep(self.cfg.sleep_time_spin)
        finally:
            self.stop()

    def rows(self) -> t.Iterator[dict[str, t.Any]]:
        yield from self.total_state.rows(self.devices)

    def on_stopped(self) -> None:
        if self.running and all(d.stopped for d in self.device_recorders):
            self.stop()

    def start(self) -> None:
        self.live_thread.start()
        self.device_thread.start()
        for d in self.device_recorders:
            d.start()

        self.running.set()

    def stop(self) -> None:
        self.running.clear()
        self.live_thread.stop()
        self.device_thread.stop()
        for d in self.device_recorders:
            d.stop()
        self.stopped.set()

    def check_devices(self):
        times.sleep(self.cfg.sleep_time_device)
        self.devices = device.input_names()

    def update_live(self):
        times.sleep(self.cfg.sleep_time_live)
        self.live.update()
