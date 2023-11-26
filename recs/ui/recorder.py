import contextlib
import typing as t

from rich.table import Table
from threa import HasThread, Runnable

from recs.base import RecsError, state, times
from recs.cfg import Cfg, device

from . import live
from .device_recorder import DeviceRecorder
from .device_tracks import device_tracks

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
        self.start_time = times.time()

        tracks = self.device_tracks.values()

        def make_recorder(t) -> DeviceRecorder:
            dr = DeviceRecorder(cfg, t, self.stop, self.record_callback)
            dr.stopped.on_set.append(self.on_stopped)
            return dr

        self.device_recorders = tuple(make_recorder(t) for t in tracks)
        self.live_thread = HasThread(self._live_thread)

        def device_state(t) -> state.DeviceState:
            return {i.channels_name: state.ChannelState() for i in t}

        self.state = {d.name: device_state(t) for d, t in self.device_tracks.items()}
        self.total_state = state.ChannelState()

    def run(self) -> None:
        self.start()
        self.live_thread.start()
        for d in self.device_recorders:
            d.start()

        try:
            with contextlib.ExitStack() as stack:
                for d in self.device_recorders:
                    stack.enter_context(d)
                stack.enter_context(self.live)

                while self.running:
                    times.sleep(self.cfg.sleep_time)
        finally:
            self.stop()

    def record_callback(self, state: state.RecorderState) -> None:
        for dname, d in state.items():
            for cname, c in d.items():
                self.state[dname][cname] += c
                self.total_state += c

    @property
    def elapsed_time(self) -> float:
        return times.time() - self.start_time

    def rows(self) -> t.Iterator[dict[str, t.Any]]:
        yield {
            'time': self.elapsed_time,
            'recorded': self.total_state.recorded_time,
            'file_size': self.total_state.file_size,
            'file_count': self.total_state.file_count,
        }
        for v in self.device_recorders:
            yield from v.rows()

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
