import json
import os
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, ValidationError


class ManifestHeader(BaseModel):
    model_config = ConfigDict(extra='forbid')

    type: str = 'header'
    version: int = 2
    started_at: str
    session_id: str | None = None
    continued_from: str | None = None


class ManifestEvent(BaseModel):
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
    current_path: str | None = None
    continued_at: str | None = None


class ManifestFile(BaseModel):
    model_config = ConfigDict(extra='forbid')

    type: str
    timestamp: str
    frame_count: int | None = None
    path: str
    track: int
    channels: int
    sample_rate: int
    bit_depth: int
    source: str | None = None


class ManifestWarning(BaseModel):
    model_config = ConfigDict(extra='forbid')

    type: str = 'warning'
    timestamp: str
    message: str


class ManifestFooter(BaseModel):
    model_config = ConfigDict(extra='forbid')

    type: str = 'footer'
    ended_at: str
    duration: float


class SessionManifest(BaseModel):
    model_config = ConfigDict(extra='forbid')

    started_at: str
    session_id: str | None = None
    continued_from: str | None = None
    ended_at: str | None = None
    duration: float | None = None
    events: list[ManifestEvent] = Field(default_factory=list)
    files: list[ManifestFile] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


ManifestRecord = (
    ManifestEvent | ManifestFile | ManifestFooter | ManifestHeader | ManifestWarning
)


class SessionManifestWriter:
    def __init__(
        self,
        path: Path,
        started_at: str,
        session_id: str | None = None,
        continued_from: str | None = None,
    ) -> None:
        self.path = _available_path(path)
        self.path.parent.mkdir(exist_ok=True, parents=True)
        self.fp = self.path.open('a')
        self.write(
            ManifestHeader(
                started_at=started_at,
                session_id=session_id,
                continued_from=continued_from,
            )
        )

    def write(
        self,
        record: ManifestRecord,
    ) -> None:
        self.fp.write(record.model_dump_json(exclude_none=True) + '\n')
        self.fp.flush()
        os.fsync(self.fp.fileno())

    def close(self) -> None:
        self.fp.close()


def read(path: Path) -> SessionManifest:
    records, errors = _read_records(path)
    header = next((r for r in records if isinstance(r, ManifestHeader)), None)
    footer = next((r for r in reversed(records) if isinstance(r, ManifestFooter)), None)
    return SessionManifest(
        started_at=header.started_at if header else '',
        session_id=header.session_id if header else None,
        continued_from=header.continued_from if header else None,
        ended_at=footer.ended_at if footer else None,
        duration=footer.duration if footer else None,
        events=[r for r in records if isinstance(r, ManifestEvent)],
        files=[r for r in records if isinstance(r, ManifestFile)],
        warnings=[r.message for r in records if isinstance(r, ManifestWarning)],
        errors=errors,
    )


def timestamp_to_json(timestamp: float) -> str:
    return (
        datetime.fromtimestamp(timestamp, timezone.utc)
        .isoformat(timespec='milliseconds')
        .replace('+00:00', 'Z')
    )


def _read_records(
    path: Path,
) -> tuple[list[ManifestRecord], list[str]]:
    records: list[ManifestRecord] = []
    errors: list[str] = []
    lines = path.read_text().splitlines()
    for i, line in enumerate(lines, 1):
        if not line:
            continue
        try:
            records.append(_parse_record(line))
        except (json.JSONDecodeError, ValidationError, ValueError) as e:
            prefix = 'truncated final line' if i == len(lines) else f'line {i}'
            errors.append(f'{path}: {prefix}: {e}')
    return records, errors


def _parse_record(
    line: str,
) -> ManifestRecord:
    data = json.loads(line)
    if not isinstance(data, dict):
        raise ValueError('manifest line must be a JSON object')
    record_type = data.get('type')
    if record_type == 'header':
        return ManifestHeader.model_validate(data)
    if record_type in {'file_finished', 'file_started'}:
        return ManifestFile.model_validate(data)
    if record_type == 'footer':
        return ManifestFooter.model_validate(data)
    if record_type == 'warning':
        return ManifestWarning.model_validate(data)
    if isinstance(record_type, str):
        return ManifestEvent.model_validate(data)
    raise ValueError('manifest line is missing a string type')


def _available_path(path: Path) -> Path:
    if not path.exists():
        return path

    index = 1
    while True:
        candidate = path.with_stem(f'{path.stem}-{index}')
        if not candidate.exists():
            return candidate
        index += 1
