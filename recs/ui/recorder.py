import typing as t
from multiprocessing import connection

from threa import HasThread, Runnables

from recs.base import RecsError
from recs.cfg import Cfg

from . import live
from .device_names import DeviceNames
from .device_process import DeviceProcess
from .device_recorder import POLL_TIMEOUT
from .device_tracks import device_tracks
from .full_state import FullState


class Recorder(Runnables):
    def __init__(self, cfg: Cfg) -> None:
        super().__init__()

        if not (tracks := device_tracks(cfg)):
            raise RecsError('No devices or channels selected')

        self.cfg = cfg
        self.live = live.Live(self.rows, cfg)
        self.state = FullState(tracks)
        self.device_names = DeviceNames(cfg.sleep_time_device)

        processes = tuple(DeviceProcess(cfg, t) for t in tracks.values())
        self.connections = {p.connection: p for p in processes}
        ui_time = 1 / self.cfg.ui_refresh_rate
        live_thread = HasThread(self.live.update, looping=True, pre_delay=ui_time)

        self.runnables = self.live, self.device_names, *processes, live_thread

    def run_recorder(self) -> None:
        with self:
            while self.running:
                self.receive()

    def rows(self) -> t.Iterator[dict[str, t.Any]]:
        yield from self.state.rows(self.device_names.names)

    def receive(self):
        for c in connection.wait(list(self.connections), timeout=POLL_TIMEOUT):
            m = c.recv()
            for device_name, msg in m.items():
                if exit := msg.get('_exit'):
                    assert exit
                    self.connections[c].set_sent()
                    self.running.clear()
                else:
                    self.state.update({device_name: msg})

        if (t := self.cfg.total_run_time) and t <= self.state.elapsed_time:
            self.stop()
