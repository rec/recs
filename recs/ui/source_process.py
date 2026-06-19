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
        self.name = tracks[0].source.name
        self.source = tracks[0].source
        self.tracks = tracks
        self.started: bool = False

    @property
    def required_channels(self) -> int:
        return max(int(channel) for track in self.tracks for channel in track.channels)

    @property
    def is_alive(self) -> bool:
        return self.started and self.process.is_alive()

    def start(self) -> None:
        assert not self.started
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
        self.started = True
        self.stopped = False
        super().start()

    def stop(self) -> None:
        if not self.started:
            return
        self.running = False
        self.stop_event.set()

    def finish(self) -> None:
        self.stop()

    def join(self, timeout: float | None = None) -> None:
        if not self.started:
            return
        self.process.join(STOP_TIMEOUT if timeout is None else timeout)
        if self.process.is_alive():
            self.process.terminate()
            self.process.join()
        self.connection.close()
        self.running = False
        self.started = False
        self.stopped = True
