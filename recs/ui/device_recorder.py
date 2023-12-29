import os
import typing as t
from multiprocessing.connection import Connection

import numpy as np
from threa import Runnables, ThreadQueue, Wrapper

from recs.audio.channel_writer import ChannelWriter
from recs.base import cfg_raw, state, times
from recs.base.types import Active, Format
from recs.cfg import Cfg, Track
from recs.cfg.device import Update

NEW_CODE_FLAG = 'RECS_NEW_CODE' in os.environ
FINISH = 'finish'
OFFLINE_TIME = 1
POLL_TIMEOUT = 0.05


class DeviceRecorder(Runnables):
    elapsed_samples: int = 0

    def __init__(
        self,
        cfg: cfg_raw.CfgRaw,
        connection: Connection,
        tracks: t.Sequence[Track],
    ) -> None:
        self.cfg = Cfg(**cfg.asdict())
        self.connection = connection

        self.device = d = tracks[0].device
        self.name = self.cfg.aliases.display_name(d)
        self.times = self.cfg.times.scale(d.samplerate)

        cw = (ChannelWriter(cfg=self.cfg, times=self.times, track=t) for t in tracks)
        self.channel_writers = tuple(cw)
        self.timestamp = times.timestamp()
        self.queue = ThreadQueue(self.device_callback)
        self.input_stream = self.device.input_stream(
            device_callback=self.queue.put,
            sdtype=self.cfg.sdtype,
            on_error=self.stop,
        )
        super().__init__(Wrapper(self.input_stream), self.queue, *self.channel_writers)
        self.start()

        while self.running:
            if connection.poll(POLL_TIMEOUT):
                msg = connection.recv()
                if NEW_CODE_FLAG and msg == FINISH:
                    self.finish()

    def device_callback(self, update: Update) -> None:
        array = update.array
        self.timestamp = times.timestamp()

        if self.cfg.format == Format.mp3 and array.dtype == np.float32:
            # mp3 and float32 crashes every time on my machine
            array = array.astype(np.float64)

        msgs: dict[str, state.ChannelState] = {}
        for c in self.channel_writers:
            msgs[c.track.name] = c.receive_array(array, self.timestamp)

        self.elapsed_samples += len(array)
        if (t := self.times.total_run_time) and self.elapsed_samples >= t:
            self.finish()

        self.connection.send({self.device.name: msgs})

    def active(self) -> Active:
        # TODO: this does work but we should probably bypass this
        dt = times.timestamp() - self.timestamp
        return Active.offline if dt > OFFLINE_TIME else Active.active
