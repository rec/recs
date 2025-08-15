import contextlib
import os
import typing as t
from multiprocessing.connection import Connection
from queue import Empty, Queue

import numpy as np
from threa import Runnables

from recs.audio.channel_writer import ChannelWriter
from recs.base import cfg_raw
from recs.base.types import Format
from recs.cfg import Cfg, Track
from recs.cfg.source import Update

NEW_CODE_FLAG = 'RECS_NEW_CODE' in os.environ
FINISH = 'finish'
OFFLINE_TIME = 1
POLL_TIMEOUT = 0.05


class SourceRecorder(Runnables):
    sample_count: int = 0

    def __init__(
        self,
        cfg: cfg_raw.CfgRaw,
        connection: Connection,
        tracks: t.Sequence[Track],
    ) -> None:
        self.cfg = Cfg(**cfg.asdict())
        self.connection = connection

        self.source = tracks[0].source
        assert all(t.source == self.source for t in tracks)

        self.name = self.cfg.aliases.display_name(self.source)
        self.queue: Queue[Update] = Queue()
        self.times = self.cfg.times.scale(self.source.samplerate)
        self.channel_writers = tuple(
            ChannelWriter(cfg=self.cfg, times=self.times, track=t) for t in tracks
        )

        self.input_stream = self.source.input_stream(
            sdtype=self.cfg.sdtype,
            update_callback=self.queue.put,
        )
        super().__init__(self.input_stream, *self.channel_writers)

        with contextlib.suppress(KeyboardInterrupt), self:
            while self.running:
                with contextlib.suppress(Empty):
                    self._receive_update(self.queue.get(timeout=POLL_TIMEOUT))

        with contextlib.suppress(Empty):
            while True:
                self._receive_update(self.queue.get(block=False))

    def _receive_update(self, u: Update) -> None:
        if self.cfg.formats == Format.mp3 and u.array.dtype == np.float32:
            # mp3 and float32 crashes every time on my machine
            u = Update(u.array.astype(np.float64), u.timestamp)

        cb = {c: c.to_block(u.array) for c in self.channel_writers}
        should_record = self.cfg.band_mode and any(
            c.should_record(b) for c, b in cb.items()
        )
        msgs = {
            c.track.name: c.receive_update(b, u.timestamp, should_record)
            for c, b in cb.items()
        }
        self.connection.send({self.source.name: msgs})

        self.sample_count += len(u.array)
        if (t := self.times.total_run_time) and self.sample_count >= t:
            self.running = False
