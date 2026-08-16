import contextlib
import threading
from collections.abc import Callable, Sequence
from multiprocessing.connection import Connection
from pathlib import Path
from queue import Empty, Queue
from time import monotonic
from typing import Any, NamedTuple, TypeVar, cast

import numpy as np
from pydantic import BaseModel
from threa import Runnables

from recs.audio.block import Block
from recs.audio.channel_writer import ChannelWriter
from recs.base import memory
from recs.base.signals import raise_keyboard_interrupt_on_signal
from recs.base.state import ChannelState
from recs.base.types import Active, Format, SdType
from recs.cfg import time_settings
from recs.cfg.cfg import Cfg
from recs.cfg.source import Update
from recs.cfg.track import Track
from recs.cfg.track_names import DeviceTrackNames

POLL_TIMEOUT = 0.05
MAX_MERGED_WARNINGS = 64
MAX_MERGED_FILES = 512
_N = TypeVar('_N', int, float)


class BufferStats(BaseModel):
    queued_blocks: int = 0
    queued_seconds: float = 0.0
    max_queued_seconds: float = 0.0
    dropped_blocks: int = 0
    dropped_frames: int = 0
    last_drop_timestamp: float = 0.0
    max_write_seconds: float = 0.0
    source_update_age_seconds: float = 0.0
    max_source_update_age_seconds: float = 0.0
    max_source_update_send_seconds: float = 0.0


class SourceUpdate(NamedTuple):
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
    calibration: dict[str, float] | None = None
    track_layout: list[str] | None = None
    config_revisions_applied: list[int] | None = None


class SourceFailure(NamedTuple):
    message: str
    source_name: str
    exception_type: str | None = None
    exitcode: int | None = None
    final_frame_count: int | None = None
    last_callback_timestamp: float | None = None
    stop_kind: str | None = None


class SourceControl(NamedTuple):
    cfg: Cfg | None = None
    cfg_revision: int | None = None
    track_names: DeviceTrackNames | None = None
    calibration_tracks: list[str] | None = None
    tracks: list[Track] | None = None


class SourceControlHandler:
    def __init__(
        self,
        connection: Connection,
        set_cfg: Callable[[Cfg, int | None], None],
        set_track_names: Callable[[DeviceTrackNames], None],
        start_calibration: Callable[[list[str]], None],
        set_tracks: Callable[[list[Track], DeviceTrackNames], None],
    ) -> None:
        self.connection = connection
        self.set_cfg = set_cfg
        self.set_track_names = set_track_names
        self.start_calibration = start_calibration
        self.set_tracks = set_tracks

    def receive(self) -> None:
        while self.connection.poll():
            try:
                message = self.connection.recv()
            except (EOFError, OSError):
                return
            if not isinstance(message, SourceControl):
                continue
            if message.cfg is not None:
                self.set_cfg(message.cfg, message.cfg_revision)
            if message.track_names is not None:
                self.set_track_names(message.track_names)
            if message.calibration_tracks is not None:
                self.start_calibration(message.calibration_tracks)
            if message.tracks is not None:
                self.set_tracks(message.tracks, message.track_names or {})


class SourceUpdateTransport:
    def __init__(self, connection: Connection) -> None:
        self.connection = connection
        self.lock = threading.Lock()
        self.message: SourceUpdate | SourceFailure | None = None
        self.message_timestamp: float | None = None
        self.max_message_age_seconds = 0.0
        self.max_send_seconds = 0.0
        self.available = threading.Event()
        self.idle = threading.Event()
        self.idle.set()
        self.stopped = threading.Event()
        self.thread = threading.Thread(
            target=self._send,
            daemon=True,
            name='SourceUpdates',
        )

    def start(self) -> None:
        self.thread.start()

    def publish(self, message: SourceUpdate | SourceFailure) -> None:
        with self.lock:
            if self.message is None:
                self.message_timestamp = monotonic()
            if isinstance(self.message, SourceUpdate) and isinstance(
                message, SourceUpdate
            ):
                self.message = _merge_updates(self.message, message)
            else:
                self.message = message
            self.available.set()
            self.idle.clear()

    def stop(self) -> None:
        self.stopped.set()
        self.available.set()

    def finish(self) -> None:
        self.idle.wait()
        self.stop()

    def _send(self) -> None:
        while not self.stopped.is_set():
            self.available.wait()
            self.available.clear()
            with self.lock:
                message, self.message = self.message, None
                message_timestamp, self.message_timestamp = self.message_timestamp, None
            if message is None:
                continue
            message = self._with_transport_stats(message, message_timestamp)
            try:
                start = monotonic()
                self.connection.send(message)
                self.max_send_seconds = max(self.max_send_seconds, monotonic() - start)
            except (BrokenPipeError, EOFError, OSError):
                return
            with self.lock:
                if self.message is None:
                    self.idle.set()
                else:
                    self.available.set()

    def _with_transport_stats(
        self,
        message: SourceUpdate | SourceFailure,
        message_timestamp: float | None,
    ) -> SourceUpdate | SourceFailure:
        if not isinstance(message, SourceUpdate):
            return message
        age = 0.0 if message_timestamp is None else monotonic() - message_timestamp
        self.max_message_age_seconds = max(self.max_message_age_seconds, age)
        stats = message.buffer_stats or BufferStats()
        return message._replace(
            buffer_stats=stats.model_copy(
                update={
                    'source_update_age_seconds': age,
                    'max_source_update_age_seconds': self.max_message_age_seconds,
                    'max_source_update_send_seconds': self.max_send_seconds,
                }
            )
        )


class SourceFile(NamedTuple):
    path: Path
    source_name: str
    track: int
    channels: int
    sample_rate: int
    bit_depth: int
    start_frame: int | None = None
    start_timestamp: float | None = None


class BufferedUpdate(NamedTuple):
    update: Update
    start_frame: int
    end_frame: int


class SourceCalibration:
    def __init__(self, samplerate: int) -> None:
        self.samplerate = samplerate
        self.remaining: dict[str, int] = {}
        self.maximums: dict[str, float] = {}
        self.minimums: dict[str, float] = {}

    def start(self, tracks: list[str]) -> None:
        frames = max(1, round(self.samplerate / 2))
        self.remaining = dict.fromkeys(tracks, frames)
        self.maximums = dict.fromkeys(tracks, float('-inf'))
        self.minimums = dict.fromkeys(tracks, float('inf'))

    def update(self, blocks: dict['ChannelWriter', Block]) -> dict[str, float] | None:
        for writer, block in blocks.items():
            name = writer.track.name
            remaining = self.remaining.get(name)
            if remaining is None or remaining <= 0:
                continue
            measured = block[:remaining]
            scale = measured.scale
            self.maximums[name] = max(self.maximums[name], max(measured.max) / scale)
            self.minimums[name] = min(self.minimums[name], min(measured.min) / scale)
            self.remaining[name] = remaining - len(measured)

        if not self.remaining or any(self.remaining.values()):
            return None

        measurements = {
            name: time_settings.amplitude_to_db((maximum - self.minimums[name]) / 2)
            for name, maximum in self.maximums.items()
        }
        self.remaining = {}
        self.maximums = {}
        self.minimums = {}
        return measurements


class SourceFileEvents:
    def __init__(self, writers: Sequence['ChannelWriter']) -> None:
        self.file_counts = [0] * len(writers)
        self.pending_file_end_frames: dict[Path, int] = {}
        self.pending_file_end_timestamps: dict[Path, float] = {}

    def reset_writers(self, writers: Sequence['ChannelWriter']) -> None:
        self.file_counts = [0] * len(writers)

    def remember_finished_files(self, writers: Sequence['ChannelWriter']) -> None:
        for writer in writers:
            self.pending_file_end_frames.update(writer.file_end_frames)
            self.pending_file_end_timestamps.update(writer.file_end_timestamps)

    def new_files(
        self, writers: Sequence['ChannelWriter'], bit_depth: int
    ) -> tuple[list[Path], list[SourceFile]]:
        result: list[Path] = []
        records: list[SourceFile] = []
        for index, writer in enumerate(writers):
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

    def end_frames(self, writers: Sequence['ChannelWriter']) -> dict[Path, int]:
        result = self.pending_file_end_frames | {
            p: frame for w in writers for p, frame in w.file_end_frames.items()
        }
        self.pending_file_end_frames = {}
        return result

    def end_timestamps(self, writers: Sequence['ChannelWriter']) -> dict[Path, float]:
        result = self.pending_file_end_timestamps | {
            p: timestamp
            for w in writers
            for p, timestamp in w.file_end_timestamps.items()
        }
        self.pending_file_end_timestamps = {}
        return result


class InputBuffer:
    def __init__(self, cfg: Cfg, samplerate: int) -> None:
        self.cfg = cfg
        self.samplerate = samplerate
        self.block_frames = 0
        self.queue: Queue[BufferedUpdate] | None = None
        self.queue_ready = threading.Event()
        self.stats = BufferStats()
        self.timeline_frames = 0
        self.reported_dropped_frames = 0
        self.memory_low = False
        self.last_memory_check = float('-inf')

    def put(self, update: Update) -> None:
        frames = len(update.array)
        if not frames:
            return
        self.block_frames = frames
        start_frame = self.timeline_frames
        self.timeline_frames += frames
        if self._memory_low():
            self._drop(update, frames)
            return
        if self.queue is None:
            maxsize = max(
                1,
                round(
                    self.cfg.recording.audio_buffer_seconds * self.samplerate / frames
                ),
            )
            self.queue = Queue(maxsize=maxsize)
            self.queue_ready.set()
        if self.queue.full():
            self._drop(update, frames)
            return
        buffered = BufferedUpdate(update, start_frame, self.timeline_frames)
        self.queue.put_nowait(buffered)
        self._update_queue_stats()

    def get(
        self, timeout: float | None = None, *, block: bool = True
    ) -> BufferedUpdate:
        if self.queue is None:
            if block:
                self.queue_ready.wait(timeout)
        if self.queue is None:
            raise Empty
        buffered = self.queue.get(block=block, timeout=timeout)
        self.block_frames = max(1, len(buffered.update.array))
        self._update_queue_stats()
        return buffered

    def warnings(self, source_name: str, timestamp: float) -> list[str]:
        warnings: list[str] = []
        if self.stats.dropped_frames > self.reported_dropped_frames:
            dropped = self.stats.dropped_frames - self.reported_dropped_frames
            warnings.append(
                f'Device {source_name}: Dropped {dropped} frames in processing'
            )
            self.reported_dropped_frames = self.stats.dropped_frames

        if self.queue is None:
            return warnings
        return warnings

    def _update_queue_stats(self) -> None:
        if self.queue is None:
            return
        self.stats.queued_blocks = self.queue.qsize()
        self.stats.queued_seconds = (
            self.stats.queued_blocks * self.block_frames / self.samplerate
        )
        self.stats.max_queued_seconds = max(
            self.stats.max_queued_seconds,
            self.stats.queued_seconds,
        )

    def _drop(self, update: Update, frames: int) -> None:
        self.stats.dropped_blocks += 1
        self.stats.dropped_frames += frames
        self.stats.last_drop_timestamp = update.timestamp

    def _memory_low(self) -> bool:
        now = monotonic()
        if now - self.last_memory_check >= self.cfg.recording.memory_check_period:
            self.last_memory_check = now
            available = memory.available_bytes()
            reserve = self.cfg.recording.memory_reserve_megabytes * 1_000_000
            self.memory_low = available is not None and available < reserve
        return self.memory_low


class SourceRecorder(Runnables):
    sample_count: int = 0

    def __init__(
        self,
        cfg: Cfg,
        control_connection: Connection,
        stop_event: Any,
        tracks: Sequence[Track],
        update_transport: SourceUpdateTransport,
        track_names: DeviceTrackNames | None = None,
    ) -> None:
        self.cfg = cfg
        self.stop_event = stop_event
        self.update_transport = update_transport

        self.source = tracks[0].source
        assert all(t.source == self.source for t in tracks)

        self.name = self.cfg.aliases.display_name(self.source)
        self.buffer = InputBuffer(self.cfg, self.source.samplerate)
        self.times = self.cfg.times.scale(self.source.samplerate)
        self.channel_writers = tuple(
            ChannelWriter(cfg=self.cfg, times=self.times, track=t) for t in tracks
        )
        self._set_track_names(track_names or {})
        self.file_events = SourceFileEvents(self.channel_writers)
        self.pending_active_channels: set[int] = set()
        self.pending_config_revisions: list[int] = []
        self.pending_track_layout: list[str] | None = None
        self.calibration = SourceCalibration(self.source.samplerate)
        self.control = SourceControlHandler(
            control_connection,
            self._set_cfg,
            self._set_track_names,
            self.calibration.start,
            self._set_tracks,
        )

        self.input_stream = self.source.input_stream(
            sdtype=cast(SdType, self.cfg.audio.sdtype),
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
                    update = self.buffer.get(timeout=POLL_TIMEOUT)
                except Empty:
                    if not self.input_stream.running:
                        break
                else:
                    self.control.receive()
                    self._receive_update(update)

        with contextlib.suppress(Empty):
            while True:
                update = self.buffer.get(block=False)
                self.control.receive()
                self._receive_update(update)

    def _set_track_names(self, track_names: DeviceTrackNames) -> None:
        for writer in self.channel_writers:
            writer.set_track_names(track_names)

    def _set_cfg(self, cfg: Cfg, revision: int | None = None) -> None:
        self.cfg = cfg
        self.buffer.cfg = cfg
        self.times = cfg.times.scale(self.source.samplerate)
        for writer in self.channel_writers:
            writer.set_cfg(cfg, self.times)
        if revision is not None:
            self.pending_config_revisions.append(revision)

    def _set_tracks(self, tracks: list[Track], track_names: DeviceTrackNames) -> None:
        for writer in self.channel_writers:
            if writer.active == Active.active:
                self.pending_active_channels.update(writer.track.channels)
            writer.stop()
        self.file_events.remember_finished_files(self.channel_writers)
        self.channel_writers = tuple(
            ChannelWriter(cfg=self.cfg, times=self.times, track=track)
            for track in tracks
        )
        self._set_track_names(track_names)
        self.file_events.reset_writers(self.channel_writers)
        self.runnables = self.input_stream, *self.channel_writers
        self.pending_track_layout = [track.name for track in tracks]

    def _receive_update(self, u: BufferedUpdate) -> None:
        update = u.update
        if Format.mp3 in self.cfg.audio.formats and update.array.dtype == np.float32:
            # mp3 and float32 crashes every time on my machine
            update = Update(update.array.astype(np.float64), update.timestamp)
            u = BufferedUpdate(update, u.start_frame, u.end_frame)

        end_timestamp = update.timestamp + len(update.array) / self.source.samplerate
        cb = {c: c.to_block(update.array) for c in self.channel_writers}
        should_record = {c: c.should_record(b) for c, b in cb.items()}
        band_should_record = self.cfg.recording.band_mode and any(
            should_record.values()
        )
        msgs: dict[str, ChannelState] = {}
        for writer, block in cb.items():
            forced = bool(set(writer.track.channels) & self.pending_active_channels)
            msgs[writer.track.name] = writer.receive_update(
                block,
                end_timestamp,
                should_record[writer] or band_should_record or forced,
                u.end_frame,
            )
        self.pending_active_channels = set()
        calibration = self.calibration.update(cb)
        files, file_records = self.file_events.new_files(
            self.channel_writers, update.array.dtype.itemsize * 8
        )
        stats = self.buffer.stats.model_copy()
        stats.max_write_seconds = max(
            stats.max_write_seconds,
            *(state.max_write_seconds for state in msgs.values()),
        )
        buffer_warnings = self.buffer.warnings(self.source.name, update.timestamp)
        if update.status:
            if update.status == 'input overflow':
                buffer_warnings.append(
                    f'Device {self.source.name}: Dropped frame in PortAudio'
                )
            else:
                buffer_warnings.append(
                    f'Device {self.source.name} input status: {update.status}'
                )
        track_layout, self.pending_track_layout = self.pending_track_layout, None
        config_revisions, self.pending_config_revisions = (
            self.pending_config_revisions,
            [],
        )
        file_end_frames = self.file_events.end_frames(self.channel_writers)
        file_end_timestamps = self.file_events.end_timestamps(self.channel_writers)
        self.update_transport.publish(
            SourceUpdate(
                channels=msgs,
                files=files,
                frames=len(update.array),
                source_name=self.source.key,
                timestamp=end_timestamp,
                buffer_stats=stats,
                buffer_warnings=buffer_warnings,
                file_records=file_records,
                file_end_frames=file_end_frames,
                file_end_timestamps=file_end_timestamps,
                frame_count=u.end_frame,
                calibration=calibration,
                track_layout=track_layout,
                config_revisions_applied=config_revisions or None,
            )
        )

        self.sample_count += len(update.array)
        if (total := self.times.total_run_time) and self.sample_count >= total:
            self.running = False


def _merge_updates(first: SourceUpdate, second: SourceUpdate) -> SourceUpdate:
    file_records = {r.path: r for r in first.file_records or []}
    file_records.update({r.path: r for r in second.file_records or []})
    files = _merge_files(first.files, second.files)
    file_paths = set(files)
    return SourceUpdate(
        channels=second.channels,
        files=files,
        frames=first.frames + second.frames,
        source_name=second.source_name,
        timestamp=second.timestamp,
        buffer_stats=second.buffer_stats,
        buffer_warnings=_merge_warnings(first.buffer_warnings, second.buffer_warnings),
        file_records=[r for r in file_records.values() if r.path in file_paths],
        file_end_frames=_merge_file_map(first.file_end_frames, second.file_end_frames),
        file_end_timestamps=_merge_file_map(
            first.file_end_timestamps, second.file_end_timestamps
        ),
        frame_count=second.frame_count,
        calibration=first.calibration or second.calibration,
        track_layout=first.track_layout or second.track_layout,
        config_revisions_applied=[
            *(first.config_revisions_applied or []),
            *(second.config_revisions_applied or []),
        ]
        or None,
    )


def _merge_files(first: list[Path], second: list[Path]) -> list[Path]:
    return list(dict.fromkeys([*first, *second]))[-MAX_MERGED_FILES:]


def _merge_warnings(
    first: list[str] | None, second: list[str] | None
) -> list[str] | None:
    warnings = [*(first or []), *(second or [])]
    if len(warnings) <= MAX_MERGED_WARNINGS:
        return warnings or None
    dropped = len(warnings) - MAX_MERGED_WARNINGS + 1
    return [
        f'Dropped {dropped} older source warnings while parent was busy',
        *warnings[-(MAX_MERGED_WARNINGS - 1) :],
    ]


def _merge_file_map(
    first: dict[Path, _N] | None,
    second: dict[Path, _N] | None,
) -> dict[Path, _N]:
    combined = (first or {}) | (second or {})
    keys = list(combined)[-MAX_MERGED_FILES:]
    return {k: combined[k] for k in keys}
