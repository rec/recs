import contextlib
import typing as t
from multiprocessing.connection import Connection
from pathlib import Path
from queue import Empty, Queue

import numpy as np
from threa import Runnables

from recs.audio.channel_writer import ChannelWriter
from recs.base import cfg_raw
from recs.base.state import ChannelState
from recs.base.types import Format
from recs.cfg import Cfg, Track
from recs.cfg.source import Update

POLL_TIMEOUT = 0.05


class SourceUpdate(t.NamedTuple):
    channels: dict[str, ChannelState]
    files: list[Path]
    frames: int
    source_name: str


class SourceRecorder(Runnables):
    sample_count: int = 0

    def __init__(
        self,
        cfg: cfg_raw.CfgRaw,
        connection: Connection,
        stop_event: t.Any,
        tracks: t.Sequence[Track],
    ) -> None:
        self.cfg = Cfg(**cfg.model_dump())
        self.connection = connection
        self.stop_event = stop_event

        self.source = tracks[0].source
        assert all(t.source == self.source for t in tracks)

        self.name = self.cfg.aliases.display_name(self.source)
        self.queue: Queue[Update] = Queue()
        self.times = self.cfg.times.scale(self.source.samplerate)
        self.channel_writers = tuple(
            ChannelWriter(cfg=self.cfg, times=self.times, track=t) for t in tracks
        )
        self.file_counts = [0] * len(self.channel_writers)

        self.input_stream = self.source.input_stream(
            sdtype=self.cfg.sdtype,
            update_callback=self.queue.put,
        )
        super().__init__(self.input_stream, *self.channel_writers)

        with contextlib.suppress(KeyboardInterrupt), self:
            while self.running and not self.stop_event.is_set():
                try:
                    self._receive_update(self.queue.get(timeout=POLL_TIMEOUT))
                except Empty:
                    if not self.input_stream.running:
                        break

        with contextlib.suppress(Empty):
            while True:
                self._receive_update(self.queue.get(block=False))

    def _receive_update(self, u: Update) -> None:
        if Format.mp3 in self.cfg.formats and u.array.dtype == np.float32:
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
        self.connection.send(
            SourceUpdate(
                channels=msgs,
                files=self._new_files(),
                frames=len(u.array),
                source_name=self.source.name,
            )
        )

        self.sample_count += len(u.array)
        if (total := self.times.total_run_time) and self.sample_count >= total:
            self.running = False

    def _new_files(self) -> list[Path]:
        result: list[Path] = []
        for index, writer in enumerate(self.channel_writers):
            result.extend(writer.files_written[self.file_counts[index] :])
            self.file_counts[index] = len(writer.files_written)
        return result
