import multiprocessing as mp
import typing as t
from multiprocessing.connection import Connection

import threa

from recs.base import state
from recs.cfg import Cfg, Track

POLL_TIMEOUT = 0.05

FINISH = 'finish'


def poll_recv(conn: Connection) -> t.Any:
    return conn.poll(POLL_TIMEOUT) and conn.recv()


class DeviceProxy(threa.Runnables):
    def __init__(
        self,
        cfg: Cfg,
        receive_message: t.Callable[[state.RecorderState], None],
        tracks: t.Sequence[Track],
    ) -> None:
        from .device_recorder import DeviceRecorder

        self.receive_message = receive_message

        self.connection, child = mp.Pipe()
        poll = threa.HasThread(self.poll_for_messages, looping=True)

        kwargs = {'raw_cfg': cfg.cfg, 'connection': child, 'tracks': tracks}
        process = mp.Process(target=DeviceRecorder, kwargs=kwargs)

        super().__init__(poll, threa.Wrapper(process))

    def poll_for_messages(self) -> None:
        while self.running:
            if message := poll_recv(self.connection):
                self.receive_message(message)
