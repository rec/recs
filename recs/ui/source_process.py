import multiprocessing as mp
import typing as t
from multiprocessing import connection

from threa import Runnable

from recs.base.cfg_raw import CfgRaw
from recs.cfg import Track

from .source_recorder import SourceRecorder

STOP_TIMEOUT = 2.0


class SourceProcess(Runnable):
    connection: connection.Connection
    process: mp.Process
    stop_event: t.Any

    def __init__(self, cfg: CfgRaw, tracks: t.Sequence[Track]) -> None:
        self.cfg = cfg
        self.tracks = tracks

    @property
    def is_alive(self) -> bool:
        return self.process.is_alive()

    def start(self) -> None:
        self.connection, child = mp.Pipe()
        self.stop_event = mp.Event()
        kwargs = {
            'cfg': self.cfg,
            'connection': child,
            'stop_event': self.stop_event,
            'tracks': self.tracks,
        }
        self.process = mp.Process(target=SourceRecorder, kwargs=kwargs)
        self.process.start()
        self.stopped = False
        super().start()

    def stop(self) -> None:
        self.running = False
        self.stop_event.set()

    def finish(self) -> None:
        self.running = False

    def join(self, timeout: float | None = None) -> None:
        self.process.join(STOP_TIMEOUT if timeout is None else timeout)
        if self.process.is_alive():
            self.process.terminate()
            self.process.join()
        self.connection.close()
        self.stopped = True
