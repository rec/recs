from pathlib import Path
from typing import NamedTuple

from pydantic import BaseModel
from ufor.recording import AudioSpan

from recs.base.state import ChannelState
from recs.base.waveform import (
    WaveformBatchData,
    WaveformLayoutData,
)
from recs.cfg.cfg import Cfg
from recs.cfg.track import Track
from recs.cfg.track_names import SourceTrackNames
from recs.recording.capture_events import SourceFile
from recs.recording.session_record import AudioTimelineRecord


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
    track_state_frames: dict[str, int] | None = None
    track_state_timestamps: dict[str, float] | None = None
    buffer_stats: BufferStats | None = None
    buffer_warnings: list[str] | None = None
    file_records: list['SourceFile'] | None = None
    file_end_frames: dict[Path, int] | None = None
    file_end_timestamps: dict[Path, float] | None = None
    frame_count: int | None = None
    calibration: dict[str, float] | None = None
    track_layout: list[str] | None = None
    config_revisions_applied: list[int] | None = None
    waveform_layout: WaveformLayoutData | None = None
    waveform_batches: list[WaveformBatchData] | None = None
    writing_enabled: bool | None = None
    write_error: str | None = None
    file_spans: dict[Path, list[AudioSpan]] | None = None
    timelines: list[AudioTimelineRecord] | None = None
    finished_files: list[Path] | None = None
    discarded_files: list[Path] | None = None


class SourceFailure(NamedTuple):
    message: str
    source_name: str
    exception_type: str | None = None
    exitcode: int | None = None
    final_frame_count: int | None = None
    last_callback_timestamp: float | None = None
    stop_kind: str | None = None
    portaudio_code: int | None = None
    host_api: str | None = None
    host_error_code: int | None = None
    host_error_message: str | None = None
    device_unavailable: bool = False


class SourceControl(NamedTuple):
    cfg: Cfg | None = None
    cfg_revision: int | None = None
    session_directory: Path | None = None
    track_names: SourceTrackNames | None = None
    calibration_tracks: list[str] | None = None
    tracks: list[Track] | None = None
    waveforms_enabled: bool | None = None
    writing_enabled: bool | None = None
