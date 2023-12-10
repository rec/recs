import multiprocessing as mp
import typing as t
from multiprocessing.connection import Connection

from overrides import override
from threa import IsThread

from recs.base import cfg_raw, state, types
from recs.cfg import Cfg, Track

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
        super().__init__()

        self._callback = callback

        self.to_process, self.from_process = pipe = mp.Pipe()
        self.process = mp.Process(target=device_process, args=(cfg.cfg, tracks, *pipe))
        self.process_stopped = False
        self.stop_all = stop_all

    @override
    def start(self) -> None:
        self.process.start()
        super().start()

    @override
    def stop(self) -> None:
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
            import traceback

            traceback.print_exc()
            self.stop()


def device_process(
    cfg: cfg_raw.CfgRaw,
    tracks: t.Sequence[Track],
    from_process: Connection,
    to_process: Connection,
) -> None:
    from .device_recorder import DeviceRecorder

    def stop_all() -> None:
        from_process.send(STOP)

    recorder = DeviceRecorder(Cfg(**cfg.asdict()), tracks, stop_all, from_process.send)
    recorder.start()
