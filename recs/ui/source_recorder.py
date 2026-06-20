import contextlib
import typing as t
from multiprocessing.connection import Connection
from pathlib import Path
from queue import Empty, Queue

import numpy as np
from threa import Runnables

from recs.audio.channel_writer import ChannelWriter
from recs.base.signals import raise_keyboard_interrupt_on_signal
from recs.base.state import ChannelState
from recs.base.types import Format, SdType
from recs.cfg import Cfg, Track
from recs.cfg.source import Update

POLL_TIMEOUT = 0.05


class SourceUpdate(t.NamedTuple):
    channels: dict[str, ChannelState]
    files: list[Path]
    frames: int
    source_name: str
    file_records: list['SourceFile'] | None = None


class SourceFile(t.NamedTuple):
    path: Path
    source_name: str
    track: int
    channels: int
    sample_rate: int
    bit_depth: int


class SourceRecorder(Runnables):
    sample_count: int = 0

    def __init__(
        self,
        cfg: Cfg,
        connection: Connection,
        stop_event: t.Any,
        tracks: t.Sequence[Track],
    ) -> None:
        self.cfg = cfg
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
            sdtype=t.cast(SdType, self.cfg.audio.sdtype),
            update_callback=self.queue.put,
        )
        super().__init__(self.input_stream, *self.channel_writers)

        with raise_keyboard_interrupt_on_signal(), contextlib.suppress(
            KeyboardInterrupt
        ), self:
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
        if Format.mp3 in self.cfg.audio.formats and u.array.dtype == np.float32:
            # mp3 and float32 crashes every time on my machine
            u = Update(u.array.astype(np.float64), u.timestamp)

        cb = {c: c.to_block(u.array) for c in self.channel_writers}
        should_record = self.cfg.recording.band_mode and any(
            c.should_record(b) for c, b in cb.items()
        )
        msgs = {
            c.track.name: c.receive_update(b, u.timestamp, should_record)
            for c, b in cb.items()
        }
        files, file_records = self._new_files(u.array.dtype.itemsize * 8)
        self.connection.send(
            SourceUpdate(
                channels=msgs,
                files=files,
                frames=len(u.array),
                source_name=self.source.name,
                file_records=file_records,
            )
        )

        self.sample_count += len(u.array)
        if (total := self.times.total_run_time) and self.sample_count >= total:
            self.running = False

    def _new_files(self, bit_depth: int) -> tuple[list[Path], list[SourceFile]]:
        result: list[Path] = []
        records: list[SourceFile] = []
        for index, writer in enumerate(self.channel_writers):
            new_files = writer.files_written[self.file_counts[index] :]
            result.extend(new_files)
            records.extend(
                SourceFile(
                    path=path,
                    source_name=writer.track.source.name,
                    track=writer.track.channels[0],
                    channels=len(writer.track.channels),
                    sample_rate=writer.track.source.samplerate,
                    bit_depth=bit_depth,
                )
                for path in new_files
            )
            self.file_counts[index] = len(writer.files_written)
        return result, records
