import json
import multiprocessing as mp
import typing as t
from multiprocessing import connection

from threa import HasThread, Runnables, Wrapper

from recs.base import RecsError
from recs.cfg import Cfg, Track, device

from . import live
from .device_recorder import POLL_TIMEOUT, DeviceRecorder
from .device_tracks import device_tracks
from .full_state import FullState


class Recorder(Runnables):
    def __init__(self, cfg: Cfg) -> None:
        super().__init__()

        if not (all_tracks := list(device_tracks(cfg))):
            raise RecsError('No channels selected')

        self.cfg = cfg
        self.live = live.Live(self.rows, cfg)
        self.state = FullState(all_tracks)
        self.names = device.input_names()
        self.connections: list[connection.Connection] = []
        self.processes: list[mp.Process] = []

        for _, tracks in all_tracks:
            connection, child = mp.Pipe()
            self.connections.append(connection)
            kwargs = {'cfg': cfg.cfg, 'connection': child, 'tracks': tracks}
            process = mp.Process(target=DeviceRecorder, kwargs=kwargs)
            self.processes.append(process)

        ui_time = 1 / self.cfg.ui_refresh_rate
        live_thread = HasThread(
            self.live.update, looping=True, name='LiveUpdate', pre_delay=ui_time
        )

        self.runnables = *(Wrapper(p) for p in self.processes), live_thread, self.live

    def rows(self) -> t.Iterator[dict[str, t.Any]]:
        yield from self.state.rows(self.names)

    def run(self) -> None:
        try:
            self._run()
        finally:
            if self.cfg.calibrate or self.cfg.verbose:
                print(json.dumps(self.state.db_ranges(), indent=2))

    def _run(self) -> None:
        with self:
            while self.running and all(p.is_alive() for p in self.processes):
                for c in connection.wait(self.connections, timeout=POLL_TIMEOUT):
                    conn = t.cast(connection.Connection, c)
                    self.state.update(conn.recv())
