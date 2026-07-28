import contextlib
import math
import typing as t
from multiprocessing.connection import Connection
from pathlib import Path
from queue import Empty, Full, Queue

import numpy as np
from pydantic import BaseModel
from threa import Runnables

from recs.audio.channel_writer import ChannelWriter
from recs.base.signals import raise_keyboard_interrupt_on_signal
from recs.base.state import ChannelState
from recs.base.types import Format, SdType
from recs.cfg import Cfg, Track
from recs.cfg.source import Update

POLL_TIMEOUT = 0.05
DEFAULT_BLOCK_FRAMES = 512


class BufferStats(BaseModel):
    queued_blocks: int = 0
    queued_seconds: float = 0.0
    max_queued_seconds: float = 0.0
    dropped_blocks: int = 0
    dropped_frames: int = 0
    last_drop_timestamp: float = 0.0


class SourceUpdate(t.NamedTuple):
    channels: dict[str, ChannelState]
    files: list[Path]
    frames: int
    source_name: str
    timestamp: float | None = None
    buffer_stats: BufferStats | None = None
    buffer_warnings: list[str] | None = None
    file_records: list['SourceFile'] | None = None
    file_end_frames: dict[Path, int] | None = None
    file_end_timestamps: dict[Path, float] | None = None
    frame_count: int | None = None


class SourceFailure(t.NamedTuple):
    message: str
    source_name: str


class SourceFile(t.NamedTuple):
    path: Path
    source_name: str
    track: int
    channels: int
    sample_rate: int
    bit_depth: int
    start_frame: int | None = None
    start_timestamp: float | None = None


class BufferedUpdate(t.NamedTuple):
    update: Update
    start_frame: int
    end_frame: int


class InputBuffer:
    def __init__(self, cfg: Cfg, samplerate: int) -> None:
        self.cfg = cfg
        self.samplerate = samplerate
        self.block_frames = DEFAULT_BLOCK_FRAMES
        self.queue: Queue[BufferedUpdate] = Queue(maxsize=self._max_blocks())
        self.stats = BufferStats()
        self.timeline_frames = 0
        self.reported_dropped_frames = 0
        self.last_pressure_warning = 0.0
        self.pressure_reported = False

    def put(self, update: Update) -> None:
        self.block_frames = max(1, len(update.array))
        start_frame = self.timeline_frames
        self.timeline_frames += len(update.array)
        buffered = BufferedUpdate(update, start_frame, self.timeline_frames)
        try:
            self.queue.put_nowait(buffered)
            self._update_queue_stats()
        except Full:
            self.stats.dropped_blocks += 1
            self.stats.dropped_frames += len(update.array)
            self.stats.last_drop_timestamp = update.timestamp

    def get(
        self, timeout: float | None = None, *, block: bool = True
    ) -> BufferedUpdate:
        buffered = self.queue.get(block=block, timeout=timeout)
        self.block_frames = max(1, len(buffered.update.array))
        self._update_queue_stats()
        return buffered

    def warnings(self, source_name: str, timestamp: float) -> list[str]:
        warnings: list[str] = []
        if self.stats.dropped_frames > self.reported_dropped_frames:
            dropped = self.stats.dropped_frames - self.reported_dropped_frames
            warnings.append(
                f'Device {source_name} audio buffer overflow: dropped {dropped} frames'
            )
            self.reported_dropped_frames = self.stats.dropped_frames

        fraction = self.queue.qsize() / self.queue.maxsize
        period = self.cfg.recording.buffer_status_period
        if fraction < self.cfg.recording.buffer_warning_fraction:
            self.pressure_reported = False
        elif (
            not self.pressure_reported
            or timestamp - self.last_pressure_warning >= period
        ):
            seconds = self.stats.queued_seconds
            warnings.append(
                f'Device {source_name} audio buffer pressure: '
                f'{seconds:.3f} seconds queued'
            )
            self.last_pressure_warning = timestamp
            self.pressure_reported = True
        return warnings

    def _update_queue_stats(self) -> None:
        self.stats.queued_blocks = self.queue.qsize()
        self.stats.queued_seconds = (
            self.stats.queued_blocks * self.block_frames / self.samplerate
        )
        self.stats.max_queued_seconds = max(
            self.stats.max_queued_seconds,
            self.stats.queued_seconds,
        )

    def _max_blocks(self) -> int:
        seconds = self.cfg.recording.audio_buffer_seconds
        return max(1, math.ceil(seconds * self.samplerate / DEFAULT_BLOCK_FRAMES))


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
        self.buffer = InputBuffer(self.cfg, self.source.samplerate)
        self.times = self.cfg.times.scale(self.source.samplerate)
        self.channel_writers = tuple(
            ChannelWriter(cfg=self.cfg, times=self.times, track=t) for t in tracks
        )
        self.file_counts = [0] * len(self.channel_writers)

        self.input_stream = self.source.input_stream(
            sdtype=t.cast(SdType, self.cfg.audio.sdtype),
            update_callback=self.buffer.put,
        )
        super().__init__(self.input_stream, *self.channel_writers)

        with (
            raise_keyboard_interrupt_on_signal(),
            contextlib.suppress(KeyboardInterrupt),
            self,
        ):
            while self.running and not self.stop_event.is_set():
                try:
                    self._receive_update(self.buffer.get(timeout=POLL_TIMEOUT))
                except Empty:
                    if not self.input_stream.running:
                        break

        with contextlib.suppress(Empty):
            while True:
                self._receive_update(self.buffer.get(block=False))

    def _receive_update(self, u: BufferedUpdate) -> None:
        update = u.update
        if Format.mp3 in self.cfg.audio.formats and update.array.dtype == np.float32:
            # mp3 and float32 crashes every time on my machine
            update = Update(update.array.astype(np.float64), update.timestamp)
            u = BufferedUpdate(update, u.start_frame, u.end_frame)

        end_timestamp = update.timestamp + len(update.array) / self.source.samplerate
        cb = {c: c.to_block(update.array) for c in self.channel_writers}
        should_record = self.cfg.recording.band_mode and any(
            c.should_record(b) for c, b in cb.items()
        )
        msgs: dict[str, ChannelState] = {}
        for writer, block in cb.items():
            msgs[writer.track.name] = writer.receive_update(
                block, end_timestamp, should_record, u.end_frame
            )
        files, file_records = self._new_files(update.array.dtype.itemsize * 8)
        stats = self.buffer.stats.model_copy()
        buffer_warnings = self.buffer.warnings(self.source.name, update.timestamp)
        if update.status:
            buffer_warnings.append(
                f'Device {self.source.name} input status: {update.status}'
            )
        self.connection.send(
            SourceUpdate(
                channels=msgs,
                files=files,
                frames=len(update.array),
                source_name=self.source.name,
                timestamp=end_timestamp,
                buffer_stats=stats,
                buffer_warnings=buffer_warnings,
                file_records=file_records,
                file_end_frames=self._file_end_frames(),
                file_end_timestamps=self._file_end_timestamps(),
                frame_count=u.end_frame,
            )
        )

        self.sample_count += len(update.array)
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
                    start_frame=writer.file_start_frames[path],
                    start_timestamp=writer.file_start_timestamps[path],
                )
                for path in new_files
            )
            self.file_counts[index] = len(writer.files_written)
        return result, records

    def _file_end_frames(self) -> dict[Path, int]:
        result: dict[Path, int] = {}
        for writer in self.channel_writers:
            result.update(writer.file_end_frames)
        return result

    def _file_end_timestamps(self) -> dict[Path, float]:
        result: dict[Path, float] = {}
        for writer in self.channel_writers:
            result.update(writer.file_end_timestamps)
        return result
