import multiprocessing as mp
import typing as t
from threading import Lock

from overrides import override
from threa import Wrapper

from recs.cfg import Cfg, Track
from recs.ui.device_recorder import DeviceRecorder


class DeviceProcess(Wrapper):
    status: str = 'ok'
    sent: bool = False

    def __init__(self, cfg: Cfg, tracks: t.Sequence[Track]) -> None:
        self.connection, child = mp.Pipe()
        self._lock = Lock()
        kwargs = {'cfg': cfg.cfg, 'connection': child, 'tracks': tracks}
        self.process = mp.Process(target=DeviceRecorder, kwargs=kwargs)
        super().__init__(self.process)

        self.device_name = tracks[0].device.name

    def set_sent(self) -> bool:
        with self._lock:
            sent, self.sent = self.sent, True
            return not sent

    @override
    def finish(self):
        self.running = False
        if self.set_sent():
            self.connection.send(self.status)

        self.process.join()
        self.finished = True
