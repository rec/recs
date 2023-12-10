import typing as t

from overrides import override
from threa import IsThread

from recs.base import RecsError, times
from recs.cfg import Cfg, device

from . import live
from .contexts import contexts
from .device_proxy import DeviceProxy
from .device_tracks import device_tracks
from .state import State


class Recorder(IsThread):
    looping = True

    def __init__(self, cfg: Cfg) -> None:
        super().__init__()
        self.pre_delay = cfg.sleep_time_device

        self.device_tracks = device_tracks(cfg)
        if not self.device_tracks:
            raise RecsError('No devices or channels selected')

        self.cfg = cfg
        self.live = live.Live(self.rows, cfg)
        self.state = State(self.device_tracks)

        tracks = self.device_tracks.values()
        dp = (DeviceProxy(cfg, t, self.stop, self.state.update) for t in tracks)
        self.devices = tuple(dp)

        self.callback()

    def run_recorder(self) -> None:
        with contexts(self, self.live, *self.devices):
            while self.running:
                times.sleep(1 / self.cfg.ui_refresh_rate)
                self.live.update()

    def rows(self) -> t.Iterator[dict[str, t.Any]]:
        yield from self.state.rows(self.device_names)

    @override
    def callback(self) -> None:
        self.device_names = device.input_names()
