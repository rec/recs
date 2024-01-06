import os
import traceback
import typing as t
from multiprocessing.connection import Connection

import numpy as np
from threa import Runnables, ThreadQueue, Wrapper

from recs.audio.channel_writer import ChannelWriter
from recs.base import cfg_raw
from recs.base.types import Format
from recs.cfg import Cfg, Track
from recs.cfg.device import Update

NEW_CODE_FLAG = 'RECS_NEW_CODE' in os.environ
FINISH = 'finish'
OFFLINE_TIME = 1
POLL_TIMEOUT = 0.05


class DeviceRecorder(Runnables):
    sample_count: int = 0

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
        self.queue = ThreadQueue(self.device_callback, name=f'ThreadQueue-{d.name}')
        self.input_stream = self.device.input_stream(
            device_callback=self.queue.put,
            sdtype=self.cfg.sdtype,
            on_error=self.stop,
        )
        super().__init__(Wrapper(self.input_stream), self.queue, *self.channel_writers)
        self.exit: dict[str, str | int] = {}

        with self:
            while not self.exit:
                try:
                    if connection.poll(POLL_TIMEOUT):
                        if msg := connection.recv():
                            self.queue.put({'reason': msg})
                except KeyboardInterrupt:
                    # We should never get here!
                    print('Aborted', d.name)

        self.connection.send({self.device.name: {'_exit': self.exit}})

    def device_callback(self, update: Update | dict[str, t.Any]) -> None:
        if self.exit:
            return

        if isinstance(update, dict):
            self.exit = update
        else:
            try:
                self._device_callback(update)
            except Exception as e:
                self.exit = {'reason': str(e), 'traceback': traceback.format_exc()}

    def _device_callback(self, u: Update) -> None:
        if self.cfg.format == Format.mp3 and u.array.dtype == np.float32:
            # mp3 and float32 crashes every time on my machine
            u = Update(u.array.astype(np.float64), u.timestamp)

        msgs = {c.track.name: c.update(u) for c in self.channel_writers}

        self.connection.send({self.device.name: msgs})

        self.sample_count += len(u.array)
        if (t := self.times.total_run_time) and self.sample_count >= t:
            self.exit = {'reason': 'total_run_time', 'samples': self.sample_count}
