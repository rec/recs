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

        if not (tracks := list(device_tracks(cfg))):
            raise RecsError('No channels selected')

        self.cfg = cfg
        self.live = live.Live(self.rows, cfg)
        self.state = FullState(tracks)
        self.names = device.input_names()

        def process(
            tracks: t.Sequence[Track],
        ) -> tuple[connection.Connection, mp.Process]:
            connection, child = mp.Pipe()
            kwargs = {'cfg': cfg.cfg, 'connection': child, 'tracks': tracks}
            process = mp.Process(target=DeviceRecorder, kwargs=kwargs)
            return connection, process

        c, p = zip(*(process(t) for _, t in tracks))
        self.connections, self.processes = tuple(c), tuple(p)

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
