import typing as t

from threa import HasThread, Runnables

from recs.base import RecsError, state, times
from recs.cfg import Cfg, device

from . import live
from .device_proxy import DeviceProxy
from .device_tracks import device_tracks
from .full_state import FullState


class Recorder(Runnables):
    looping = True

    def __init__(self, cfg: Cfg) -> None:
        super().__init__()
        self.device_tracks = device_tracks(cfg)
        if not self.device_tracks:
            raise RecsError('No devices or channels selected')

        self.cfg = cfg
        self.live = live.Live(self.rows, cfg)
        self.state = FullState(self.device_tracks)

        self._update_device_names()
        self.device_thread = HasThread(
            self._update_device_names,
            daemon=True,
            looping=True,
            pre_delay=cfg.sleep_time_device,
        )

        tracks = self.device_tracks.values()
        devices = (DeviceProxy(cfg, t, self.stop, self._update) for t in tracks)
        self.runnables = self.live, self.device_thread, *devices

    def run_recorder(self) -> None:
        with self:
            while self.running:
                times.sleep(1 / self.cfg.ui_refresh_rate)
                self.live.update()

    def rows(self) -> t.Iterator[dict[str, t.Any]]:
        yield from self.state.rows(self.device_names)

    def _update_device_names(self) -> None:
        self.device_names = device.input_names()

    def _update(self, state: state.RecorderState) -> None:
        self.state.update(state)

        if (t := self.cfg.total_run_time) and t <= self.state.elapsed_time:
            self.stop()
