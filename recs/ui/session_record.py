import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError


class SessionHeader(BaseModel):
    model_config = ConfigDict(extra='forbid')

    type: str = 'header'
    version: Literal[3] = 3
    started_at: str
    session_id: str | None = None
    continued_from: str | None = None
    application: dict[str, str] | None = None
    metadata: dict[str, object] | None = None


class EventRecord(BaseModel):
    model_config = ConfigDict(extra='forbid')

    type: str
    timestamp: str
    frame_count: int | None = None
    start_frame: int | None = None
    dropped_blocks: int | None = None
    dropped_frames: int | None = None
    source: str | None = None
    track: str | None = None
    key: str | None = None
    label: str | None = None
    address: str | None = None
    value: object | None = None
    max_queued_seconds: float | None = None
    max_write_seconds: float | None = None
    queued_seconds: float | None = None
    path: str | None = None
    disk: str | None = None
    free_bytes: int | None = None
    estimated_seconds_remaining: float | None = None
    threshold: str | None = None
    severity: str | None = None
    reason: str | None = None
    from_path: str | None = None
    to_path: str | None = None
    from_free_bytes: int | None = None
    to_free_bytes: int | None = None
    disk_kind: str | None = None
    disk_uuid: str | None = None
    current_path: str | None = None
    continued_at: str | None = None
    cfg_revision: int | None = None
    timing_source: str | None = None
    midi_port: str | None = None
    osc_node: str | None = None
    metadata: dict[str, object] | None = None


class FileRecord(BaseModel):
    model_config = ConfigDict(extra='forbid')

    type: str
    media_type: str
    timestamp: str
    stream_id: str
    format: str
    frame_count: int | None = None
    path: str
    track_name: str | None = None
    source_channels: list[int] | None = None
    channels: int | None = None
    sample_rate: int | None = None
    bit_depth: int | None = None
    source: str | None = None
    quantity_count: int | None = Field(default=None, ge=0)
    timing_source: str | None = None
    midi_port: str | None = None
    osc_node: str | None = None
    inbound_count: int | None = None
    outbound_count: int | None = None
    decode_error_count: int | None = None
    metadata: dict[str, object] | None = None


class WarningRecord(BaseModel):
    model_config = ConfigDict(extra='forbid')

    type: str = 'warning'
    timestamp: str
    message: str


class SessionFooter(BaseModel):
    model_config = ConfigDict(extra='forbid')

    type: str = 'footer'
    ended_at: str
    duration_seconds: float


class SessionRecord(BaseModel):
    model_config = ConfigDict(extra='forbid')

    started_at: str
    session_id: str | None = None
    continued_from: str | None = None
    application: dict[str, str] | None = None
    metadata: dict[str, object] | None = None
    ended_at: str | None = None
    duration_seconds: float | None = None
    events: list[EventRecord] = Field(default_factory=list)
    files: list[FileRecord] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


Record = EventRecord | FileRecord | SessionFooter | SessionHeader | WarningRecord


class SessionRecordWriter:
    def __init__(
        self,
        path: Path,
        started_at: str,
        session_id: str | None = None,
        continued_from: str | None = None,
        sync_interval: float = 1.0,
    ) -> None:
        self.path = _available_path(path)
        self.path.parent.mkdir(exist_ok=True, parents=True)
        self.fp = self.path.open('a')
        self.sync_interval = sync_interval
        self.last_sync = float('-inf')
        self.errors: list[str] = []
        self.write(
            SessionHeader(
                started_at=started_at,
                session_id=session_id,
                continued_from=continued_from,
            ),
            sync=True,
        )

    def write(
        self,
        entry: Record,
        *,
        sync: bool = False,
    ) -> None:
        self.fp.write(entry.model_dump_json(exclude_none=True) + '\n')
        self.fp.flush()
        if sync or time.monotonic() - self.last_sync >= self.sync_interval:
            self.sync()

    def close(self) -> None:
        self.sync()
        self.fp.close()

    def sync(self) -> None:
        try:
            os.fsync(self.fp.fileno())
        except OSError as e:
            self.errors.append(f'Cannot sync record {self.path}: {e}')
        else:
            self.last_sync = time.monotonic()

    def take_errors(self) -> list[str]:
        errors, self.errors = self.errors, []
        return errors


def read(path: Path) -> SessionRecord:
    entries, errors = read_entries(path)
    header = next((e for e in entries if isinstance(e, SessionHeader)), None)
    footer = next((e for e in reversed(entries) if isinstance(e, SessionFooter)), None)
    return SessionRecord(
        started_at=header.started_at if header else '',
        session_id=header.session_id if header else None,
        continued_from=header.continued_from if header else None,
        application=header.application if header else None,
        metadata=header.metadata if header else None,
        ended_at=footer.ended_at if footer else None,
        duration_seconds=footer.duration_seconds if footer else None,
        events=[e for e in entries if isinstance(e, EventRecord)],
        files=[e for e in entries if isinstance(e, FileRecord)],
        warnings=[e.message for e in entries if isinstance(e, WarningRecord)],
        errors=errors,
    )


def read_entries(path: Path) -> tuple[list[Record], list[str]]:
    return _read_entries(path)


def timestamp_to_json(timestamp: float) -> str:
    return (
        datetime.fromtimestamp(timestamp, timezone.utc)
        .isoformat(timespec='milliseconds')
        .replace('+00:00', 'Z')
    )


def _read_entries(
    path: Path,
) -> tuple[list[Record], list[str]]:
    entries: list[Record] = []
    errors: list[str] = []
    parse_errors: list[
        tuple[int, json.JSONDecodeError | ValidationError | ValueError]
    ] = []
    last_line = 0
    with path.open() as lines:
        for i, line in enumerate(lines, 1):
            last_line = i
            line = line.rstrip('\n')
            if not line:
                continue
            try:
                entries.append(_parse_entry(line))
            except (json.JSONDecodeError, ValidationError, ValueError) as e:
                parse_errors.append((i, e))
    for i, error in parse_errors:
        prefix = 'truncated final line' if i == last_line else f'line {i}'
        errors.append(f'{path}: {prefix}: {error}')
    return entries, errors


def _parse_entry(
    line: str,
) -> Record:
    data = json.loads(line)
    if not isinstance(data, dict):
        raise ValueError('record line must be a JSON object')
    record_type = data.get('type')
    if record_type == 'header':
        return SessionHeader.model_validate(data)
    if record_type in {'file_finished', 'file_started'}:
        return FileRecord.model_validate(data)
    if record_type == 'footer':
        return SessionFooter.model_validate(data)
    if record_type == 'warning':
        return WarningRecord.model_validate(data)
    if isinstance(record_type, str):
        return EventRecord.model_validate(data)
    raise ValueError('record line is missing a string type')


def _available_path(path: Path) -> Path:
    if not path.exists():
        return path

    index = 1
    while True:
        candidate = path.with_stem(f'{path.stem}-{index}')
        if not candidate.exists():
            return candidate
        index += 1
