import multiprocessing as mp
import typing as t
from multiprocessing.connection import Connection

import threa
from overrides import override

from recs.base import state, types
from recs.cfg import Cfg, Track

POLL_TIMEOUT = 0.05
FINISH = 'finish'


def poll_recv(conn: Connection) -> t.Any:
    return conn.poll(POLL_TIMEOUT) and conn.recv()


class DeviceProxy(threa.Runnables):
    def __init__(
        self,
        cfg: Cfg,
        state_callback: t.Callable[[state.RecorderState], None],
        on_finish_message: types.Stop,
        tracks: t.Sequence[Track],
    ) -> None:
        from .device_process import DeviceProcess

        self.state_callback = state_callback

        self.connection, child = mp.Pipe()
        self.process_stopped = False
        self.on_finish_message = on_finish_message

        poll = threa.HasThread(self.poll_for_messages, looping=True)
        kwargs = {'connection': child, 'raw_cfg': cfg.cfg, 'tracks': tracks}
        process = mp.Process(target=DeviceProcess, kwargs=kwargs)

        super().__init__(poll, threa.Wrapper(process))

    @override
    def stop(self) -> None:
        self.running.clear()
        if not self.process_stopped:
            self.process_stopped = True
            self.connection.send(FINISH)

        super().stop()

    def poll_for_messages(self) -> None:
        message = poll_recv(self.connection)
        if message == FINISH:
            self.process_stopped = True
            self.on_finish_message()
        elif message:
            self.state_callback(message)
