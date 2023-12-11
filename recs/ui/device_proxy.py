import multiprocessing as mp
import typing as t
from multiprocessing.connection import Connection

from overrides import override
from threa import IsThread

from recs.base import state, types
from recs.cfg import Cfg, Track

POLL_TIMEOUT = 0.1
STOP = 'stop'


def poll_recv(conn: Connection) -> t.Any:
    return conn.poll(POLL_TIMEOUT) and conn.recv()


class DeviceProxy(IsThread):
    looping = True

    def __init__(
        self,
        cfg: Cfg,
        tracks: t.Sequence[Track],
        stop_all: types.Stop,
        callback: t.Callable[[state.RecorderState], None],
    ) -> None:
        from .device_process import DeviceProcess

        super().__init__()

        self._callback = callback

        self.connection, child = mp.Pipe()
        self.process = mp.Process(target=DeviceProcess, args=(cfg.cfg, tracks, child))
        self.process_stopped = False
        self.stop_all = stop_all

    @override
    def start(self) -> None:
        self.process.start()
        super().start()

    @override
    def stop(self) -> None:
        self.running.clear()
        if not self.process_stopped:
            self.process_stopped = True
            self.connection.send(STOP)

        self.stop_all()
        super().stop()

    @override
    def join(self, timeout: float | None = None) -> None:
        super().join(timeout)
        self.process.join(timeout)

    @override
    def callback(self) -> None:
        message = poll_recv(self.connection)
        if message == STOP:
            self.process_stopped = True
            self.stop_all()
        elif message:
            self._callback(message)
