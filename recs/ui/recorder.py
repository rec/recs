import typing as t

from threa import HasThread, Runnable

from recs.base import RecsError, times
from recs.cfg import Cfg, device

from . import live
from .contexts import contexts
from .device_proxy import DeviceProxy
from .device_tracks import device_tracks
from .total_state import TotalState


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
        self.device_recorders = tuple(self._device_recorder(t) for t in tracks)
        self.set_devices()
        self.device_thread = HasThread(
            self.set_devices, looping=True, pre_delay=cfg.sleep_time_device
        )

    def run(self) -> None:
        dv = self.device_recorders
        with contexts(self, self.live, self.device_thread, *dv):
            while self.running:
                times.sleep(1 / self.cfg.ui_refresh_rate)
                self.live.update()

    def rows(self) -> t.Iterator[dict[str, t.Any]]:
        yield from self.total_state.rows(self.devices)

    def on_stopped(self) -> None:
        if self.running and all(d.stopped for d in self.device_recorders):
            self.stop()

    def _device_recorder(self, t) -> DeviceProxy:
        return DeviceProxy(self.cfg, t, self.stop, self.total_state.update)

    def set_devices(self):
        self.devices = device.input_names()
