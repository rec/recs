import threading
from collections.abc import Callable
from multiprocessing.connection import Connection
from pathlib import Path
from time import monotonic

from recs.base.waveform import (
    WaveformBatchData,
)
from recs.cfg.cfg import Cfg
from recs.cfg.track import Track
from recs.cfg.track_names import SourceTrackNames
from recs.runtime.source_messages import (
    BufferStats,
    SourceControl,
    SourceFailure,
    SourceUpdate,
)

MAX_MERGED_WARNINGS = 64


MAX_MERGED_FILES = 512


MAX_MERGED_WAVEFORM_BATCHES = 5


class SourceControlHandler:
    def __init__(
        self,
        connection: Connection,
        set_cfg: Callable[[Cfg, int | None], None],
        set_session_directory: Callable[[Path], None],
        set_track_names: Callable[[SourceTrackNames], None],
        start_calibration: Callable[[list[str]], None],
        set_tracks: Callable[[list[Track], SourceTrackNames], None],
        set_waveforms_enabled: Callable[[bool], None],
        set_writing_enabled: Callable[[bool], None],
    ) -> None:
        self.connection = connection
        self.set_cfg = set_cfg
        self.set_session_directory = set_session_directory
        self.set_track_names = set_track_names
        self.start_calibration = start_calibration
        self.set_tracks = set_tracks
        self.set_waveforms_enabled = set_waveforms_enabled
        self.set_writing_enabled = set_writing_enabled

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
            if message.session_directory is not None:
                self.set_session_directory(message.session_directory)
            if message.track_names is not None:
                self.set_track_names(message.track_names)
            if message.calibration_tracks is not None:
                self.start_calibration(message.calibration_tracks)
            if message.tracks is not None:
                self.set_tracks(message.tracks, message.track_names or {})
            if message.waveforms_enabled is not None:
                self.set_waveforms_enabled(message.waveforms_enabled)
            if message.writing_enabled is not None:
                self.set_writing_enabled(message.writing_enabled)


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
            if self.stopped.is_set():
                return
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
                with self.lock:
                    self.stopped.set()
                    self.message = None
                    self.idle.set()
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


def _merge_updates(first: SourceUpdate, second: SourceUpdate) -> SourceUpdate:
    file_records = {r.path: r for r in first.file_records or []}
    file_records.update({r.path: r for r in second.file_records or []})
    files = _merge_files(first.files, second.files)
    file_paths = set(files)
    waveform_layout = second.waveform_layout or first.waveform_layout
    waveform_batches = _merge_waveform_batches(
        [] if second.waveform_layout is not None else first.waveform_batches,
        second.waveform_batches,
    )
    return SourceUpdate(
        channels=second.channels,
        files=files,
        frames=first.frames + second.frames,
        source_name=second.source_name,
        timestamp=second.timestamp,
        track_state_frames=_merge_track_state_values(
            first,
            second,
            first.track_state_frames,
            second.track_state_frames,
            first.frame_count,
            second.frame_count,
        ),
        track_state_timestamps=_merge_track_state_values(
            first,
            second,
            first.track_state_timestamps,
            second.track_state_timestamps,
            first.timestamp,
            second.timestamp,
        ),
        buffer_stats=second.buffer_stats,
        buffer_warnings=_merge_warnings(first.buffer_warnings, second.buffer_warnings),
        file_records=[r for r in file_records.values() if r.path in file_paths],
        file_end_frames=_merge_file_map(first.file_end_frames, second.file_end_frames),
        file_spans=_merge_file_map(first.file_spans, second.file_spans),
        timelines=[*(first.timelines or []), *(second.timelines or [])] or None,
        discarded_files=_merge_files(
            first.discarded_files or [], second.discarded_files or []
        )
        or None,
        finished_files=_merge_files(
            first.finished_files or [], second.finished_files or []
        )
        or None,
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
        waveform_layout=waveform_layout,
        waveform_batches=waveform_batches or None,
        writing_enabled=(
            second.writing_enabled
            if second.writing_enabled is not None
            else first.writing_enabled
        ),
        write_error=second.write_error or first.write_error,
    )


def _merge_track_state_values[N: (int, float)](
    first: SourceUpdate,
    second: SourceUpdate,
    first_values: dict[str, N] | None,
    second_values: dict[str, N] | None,
    first_default: N | None,
    second_default: N | None,
) -> dict[str, N] | None:
    result = dict(first_values or {})
    if first_default is not None:
        for name in first.channels:
            result.setdefault(name, first_default)
    for name, state in second.channels.items():
        previous = first.channels.get(name)
        if previous is not None and previous.is_active == state.is_active:
            continue
        value = (second_values or {}).get(name, second_default)
        if value is not None:
            result[name] = value
    return result or None


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


def _merge_waveform_batches(
    first: list[WaveformBatchData] | None,
    second: list[WaveformBatchData] | None,
) -> list[WaveformBatchData]:
    batches = [*(first or []), *(second or [])]
    if len(batches) <= MAX_MERGED_WAVEFORM_BATCHES:
        return batches
    dropped = batches[:-MAX_MERGED_WAVEFORM_BATCHES]
    batches = batches[-MAX_MERGED_WAVEFORM_BATCHES:]
    batches[0] = batches[0].model_copy(
        update={
            'dropped_batches': batches[0].dropped_batches
            + sum(1 + b.dropped_batches for b in dropped)
        }
    )
    return batches


def _merge_file_map[N](
    first: dict[Path, N] | None,
    second: dict[Path, N] | None,
) -> dict[Path, N]:
    combined = (first or {}) | (second or {})
    keys = list(combined)[-MAX_MERGED_FILES:]
    return {k: combined[k] for k in keys}
