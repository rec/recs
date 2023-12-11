import traceback
import typing as t

from overrides import override
from threa import IsThread

from recs.base import state, types
from recs.cfg import Cfg, Track

USE_DUMMY_MP = False
if USE_DUMMY_MP:
    import multiprocessing.dummy as mp

else:
    import multiprocessing as mp  # type: ignore[no-redef]
    import multiprocessing.connection

Connection = mp.connection.Connection

POLL_TIMEOUT = 0.1
STOP = 'stop'


def _poll(conn: Connection) -> t.Any:
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

        self.to_process, self.from_process = pipe = mp.Pipe()
        self.process = mp.Process(target=DeviceProcess, args=(cfg.cfg, tracks, *pipe))
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
            self.to_process.send(STOP)

        self.stop_all()
        super().stop()

    @override
    def join(self, timeout: float | None = None) -> None:
        super().join(timeout)
        self.process.join(timeout)

    @override
    def callback(self) -> None:
        try:
            message = _poll(self.from_process)
            if message == STOP:
                self.process_stopped = True
                self.stop_all()
            elif message:
                self._callback(message)
        except Exception:
            traceback.print_exc()
            self.stop()
