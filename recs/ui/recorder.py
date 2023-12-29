import multiprocessing as mp
import typing as t
from multiprocessing import connection

import threa
from threa import HasThread, Runnables

from recs.base import RecsError, times
from recs.cfg import Cfg

from . import live
from .device_names import DeviceNames
from .device_recorder import POLL_TIMEOUT, DeviceRecorder
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

        def cp(tracks) -> tuple[connection.Connection, threa.Runnable]:
            connection, child = mp.Pipe()
            kwargs = {'cfg': cfg.cfg, 'connection': child, 'tracks': tracks}
            process = mp.Process(target=DeviceRecorder, kwargs=kwargs)
            return connection, threa.Wrapper(process)

        self.connections, processes = zip(*(cp(t) for t in tracks.values()))
        receive = HasThread(self.receive, daemon=True, looping=True)

        self.runnables = self.live, self.device_names, *processes, receive

    def run_recorder(self) -> None:
        with self:
            while self.running:
                times.sleep(1 / self.cfg.ui_refresh_rate)
                self.live.update()

    def rows(self) -> t.Iterator[dict[str, t.Any]]:
        yield from self.state.rows(self.device_names.names)

    def receive(self):
        for c in connection.wait(self.connections, timeout=POLL_TIMEOUT):
            self.state.update(c.recv())

        if (t := self.cfg.total_run_time) and t <= self.state.elapsed_time:
            self.stop()
