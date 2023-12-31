import multiprocessing as mp
import typing as t
from multiprocessing import connection

import threa
from overrides import override
from threa import HasThread, Runnables

from recs.base import RecsError, times
from recs.cfg import Cfg, Track

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

        processes = tuple(Process(cfg, t) for t in tracks.values())
        self.connections = tuple(p.connection for p in processes)
        receive = HasThread(self.receive, looping=True)
        ui_time = 1 / self.cfg.ui_refresh_rate
        live_thread = HasThread(self.live.update, looping=True, pre_delay=ui_time)

        self.runnables = self.live, self.device_names, *processes, receive, live_thread

    def run_recorder(self) -> None:
        with self:
            while self.running:
                times.sleep(1 / self.cfg.ui_refresh_rate)

    def rows(self) -> t.Iterator[dict[str, t.Any]]:
        yield from self.state.rows(self.device_names.names)

    def receive(self):
        for c in connection.wait(self.connections, timeout=POLL_TIMEOUT):
            msg = c.recv()
            self.state.update(msg)

        if (t := self.cfg.total_run_time) and t <= self.state.elapsed_time:
            self.stop()


class Process(threa.Wrapper):
    status: str = 'ok'

    def __init__(self, cfg: Cfg, tracks: t.Sequence[Track]) -> None:
        self.connection, child = mp.Pipe()
        kwargs = {'cfg': cfg.cfg, 'connection': child, 'tracks': tracks}
        self.process = mp.Process(target=DeviceRecorder, kwargs=kwargs)
        super().__init__(self.process)

    @override
    def finish(self):
        self.running = False
        # self.connection.send(self.status)
        super().finish()
