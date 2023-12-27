import os
import typing as t
from multiprocessing.connection import Connection

from threa import HasThread, Runnables

from recs.base import cfg_raw
from recs.cfg import Cfg, Track

from .device_proxy import FINISH, poll_recv
from .device_recorder import DeviceRecorder

NEW_CODE_FLAG = 'RECS_NEW_CODE' in os.environ


class DeviceProcess(Runnables):
    looping = True

    def __init__(
        self,
        connection: Connection,
        raw_cfg: cfg_raw.CfgRaw,
        tracks: t.Sequence[Track],
    ) -> None:
        super().__init__()

        self.connection = connection

        cfg = Cfg(**raw_cfg.asdict())
        super().__init__(
            DeviceRecorder(cfg, tracks, connection.send),
            HasThread(self.poll_for_stop, looping=True, daemon=True),
        )
        self.start()

    def poll_for_stop(self) -> None:
        if poll_recv(self.connection) == FINISH:
            if NEW_CODE_FLAG:
                self.finish()
