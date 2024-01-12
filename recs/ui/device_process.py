import multiprocessing as mp
import typing as t
from threading import Lock

from threa import Wrapper

from recs.cfg import Cfg, Track
from recs.ui.device_recorder import DeviceRecorder


class DeviceProcess(Wrapper):
    def __init__(self, cfg: Cfg, tracks: t.Sequence[Track]) -> None:
        self.connection, child = mp.Pipe()
        self._lock = Lock()
        kwargs = {'cfg': cfg.cfg, 'connection': child, 'tracks': tracks}
        self.process = mp.Process(target=DeviceRecorder, kwargs=kwargs)
        super().__init__(self.process)

        self.device_name = tracks[0].source.name
