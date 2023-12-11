import typing as t
from multiprocessing.connection import Connection

from threa import IsThread

from recs.base import cfg_raw
from recs.cfg import Cfg, Track

from .device_proxy import STOP
from .device_recorder import DeviceRecorder


class DeviceProcess(IsThread):
    looping = True

    def __init__(
        self,
        raw_cfg: cfg_raw.CfgRaw,
        tracks: t.Sequence[Track],
        from_process: Connection,
        to_process: Connection,
    ) -> None:
        super().__init__()

        self.from_process = from_process
        self.to_process = to_process

        cfg = Cfg(**raw_cfg.asdict())
        self.recorder = DeviceRecorder(cfg, tracks, self.stop_all, from_process.send)
        self.recorder.start()

    def stop_all(self) -> None:
        self.from_process.send(STOP)
