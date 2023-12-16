import typing as t
from multiprocessing.connection import Connection

from threa import HasThread, Runnables

from recs.base import cfg_raw
from recs.cfg import Cfg, Track

from .device_proxy import STOP, poll_recv
from .device_recorder import NEW_CODE_FLAG, DeviceRecorder


class DeviceProcess(Runnables):
    looping = True

    def __init__(
        self,
        raw_cfg: cfg_raw.CfgRaw,
        tracks: t.Sequence[Track],
        connection: Connection,
    ) -> None:
        super().__init__()

        self.connection = connection

        cfg = Cfg(**raw_cfg.asdict())
        super().__init__(
            DeviceRecorder(cfg, tracks, connection.send),
            HasThread(self.callback, looping=True, daemon=True),
        )
        self.start()

    def callback(self) -> None:
        if poll_recv(self.connection) == STOP:
            if NEW_CODE_FLAG:
                self.stop()
