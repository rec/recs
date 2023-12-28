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

        self.update_device_names()
        self.device_thread = HasThread(
            self.update_device_names,
            daemon=True,
            looping=True,
            pre_delay=cfg.sleep_time_device,
        )

        def proxy(tracks) -> DeviceProxy:
            return DeviceProxy(
                cfg=cfg,
                state_callback=self.state_callback,
                tracks=tracks,
            )

        proxies = (proxy(t) for t in self.device_tracks.values())
        self.runnables = self.live, self.device_thread, *proxies

    def run_recorder(self) -> None:
        with self:
            while self.running:
                times.sleep(1 / self.cfg.ui_refresh_rate)
                self.live.update()

    def rows(self) -> t.Iterator[dict[str, t.Any]]:
        yield from self.state.rows(self.device_names)

    def update_device_names(self) -> None:
        self.device_names = device.input_names()

    def state_callback(self, state: state.RecorderState) -> None:
        self.state.update(state)

        if (t := self.cfg.total_run_time) and t <= self.state.elapsed_time:
            self.stop()
