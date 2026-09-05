from pathlib import Path

import tomlkit
from pydantic import BaseModel, Field
from reccy import logging

from . import recording_paths, session_record

REPORT_FILE = 'recs-recovery-report.toml'
LOGGER = logging.get_logger(__name__)


class SourceReport(BaseModel, frozen=True):
    source: str
    last_event_type: str
    last_timestamp: str


class TrackReport(BaseModel, frozen=True):
    media_type: str
    source: str | None = None
    track_name: str | None = None
    source_channels: list[int] | None = None
    midi_port: str | None = None
    started_files: int = 0
    finished_files: int = 0
    open_files: int = 0
    missing_files: int = 0
    likely_complete: bool = False


class DiskReport(BaseModel, frozen=True):
    event_type: str
    timestamp: str
    disk: str | None = None
    free_bytes: int | None = None
    estimated_seconds_remaining: float | None = None


class RecoveryReport(BaseModel, frozen=True):
    record: Path
    started_at: str | None = None
    last_record_type: str | None = None
    last_record_timestamp: str | None = None
    parse_errors: list[str] = Field(default_factory=list)
    open_files: list[str] = Field(default_factory=list)
    missing_files: list[str] = Field(default_factory=list)
    sources: list[SourceReport] = Field(default_factory=list)
    tracks: list[TrackReport] = Field(default_factory=list)
    disk: DiskReport | None = None


def report_unfinished_sessions(root: Path) -> list[Path]:
    if not root.exists():
        return []
    reports: list[Path] = []
    for record_path in sorted(root.rglob('session-record*.jsonl')):
        try:
            report = recovery_report(record_path)
        except OSError as e:
            LOGGER.error('Cannot inspect record %s: %s', record_path, e)
            continue
        if report is None:
            continue
        report_path = record_path.parent / REPORT_FILE
        try:
            recording_paths.write_text_atomically(report_path, _toml(report))
        except OSError as e:
            LOGGER.error('Cannot write recovery report %s: %s', report_path, e)
            continue
        LOGGER.error('%s: see %s', _summary(report), report_path.resolve())
        reports.append(report_path)
    return reports


def recovery_report(path: Path) -> RecoveryReport | None:
    records, errors = session_record.read_entries(path)
    if any(isinstance(record, session_record.SessionFooter) for record in records):
        return None
    header = next(
        (
            record
            for record in records
            if isinstance(record, session_record.SessionHeader)
        ),
        None,
    )
    files = [
        record for record in records if isinstance(record, session_record.FileRecord)
    ]
    started = {record.path: record for record in files if record.type == 'file_started'}
    finished = {record.path for record in files if record.type == 'file_finished'}
    open_files = sorted(set(started) - finished)
    missing_files = [file for file in open_files if not _file_path(path, file).exists()]
    last = next(
        (
            record
            for record in reversed(records)
            if not isinstance(record, session_record.SessionHeader)
        ),
        None,
    )
    return RecoveryReport(
        record=path,
        started_at=header.started_at if header is not None else None,
        last_record_type=last.type if last is not None else None,
        last_record_timestamp=_timestamp(last),
        parse_errors=errors,
        open_files=open_files,
        missing_files=missing_files,
        sources=_source_reports(records),
        tracks=_track_reports(files, open_files, missing_files),
        disk=_disk_report(records),
    )


def _source_reports(
    records: list[session_record.Record],
) -> list[SourceReport]:
    latest: dict[str, SourceReport] = {}
    for record in records:
        if not isinstance(record, session_record.EventRecord):
            continue
        if record.source is not None:
            latest[record.source] = SourceReport(
                source=record.source,
                last_event_type=record.type,
                last_timestamp=record.timestamp,
            )
    return sorted(latest.values(), key=lambda report: report.source)


def _track_reports(
    files: list[session_record.FileRecord],
    open_files: list[str],
    missing_files: list[str],
) -> list[TrackReport]:
    reports: dict[tuple[str, str | None, tuple[int, ...], str | None], TrackReport] = {}
    for file in files:
        key = (
            file.media_type,
            file.source,
            tuple(file.source_channels or []),
            file.midi_port,
        )
        current = reports.get(
            key,
            TrackReport(
                media_type=file.media_type,
                source=file.source,
                track_name=file.track_name,
                source_channels=file.source_channels,
                midi_port=file.midi_port,
            ),
        )
        reports[key] = current.model_copy(
            update={
                'started_files': current.started_files + (file.type == 'file_started'),
                'finished_files': current.finished_files
                + (file.type == 'file_finished'),
                'open_files': current.open_files + (file.path in open_files),
                'missing_files': current.missing_files + (file.path in missing_files),
            }
        )
    return [
        report.model_copy(
            update={
                'likely_complete': not report.open_files and not report.missing_files
            }
        )
        for report in sorted(
            reports.values(),
            key=lambda report: (
                report.media_type,
                report.source or '',
                report.source_channels or [],
                report.midi_port or '',
            ),
        )
    ]


def _disk_report(
    records: list[session_record.Record],
) -> DiskReport | None:
    for record in reversed(records):
        if not isinstance(record, session_record.EventRecord):
            continue
        if (
            record.disk is not None
            or record.free_bytes is not None
            or record.estimated_seconds_remaining is not None
        ):
            return DiskReport(
                event_type=record.type,
                timestamp=record.timestamp,
                disk=record.disk,
                free_bytes=record.free_bytes,
                estimated_seconds_remaining=record.estimated_seconds_remaining,
            )
    return None


def _timestamp(record: session_record.Record | None) -> str | None:
    if isinstance(
        record,
        session_record.EventRecord
        | session_record.FileRecord
        | session_record.WarningRecord,
    ):
        return record.timestamp
    return None


def _file_path(record_path: Path, path: str) -> Path:
    value = Path(path)
    return value if value.is_absolute() else record_path.parent / value


def _summary(report: RecoveryReport) -> str:
    counts = []
    if report.open_files:
        counts.append(_count(len(report.open_files), 'open file'))
    if report.missing_files:
        counts.append(_count(len(report.missing_files), 'missing file'))
    if report.parse_errors:
        counts.append(_count(len(report.parse_errors), 'parse error'))
    details = ', '.join(counts) if counts else 'no open files'
    return f'Unfinished session, {details}'


def _count(value: int, name: str) -> str:
    suffix = '' if value == 1 else 's'
    return f'{value} {name}{suffix}'


def _toml(report: RecoveryReport) -> str:
    values: dict[str, object] = {
        'record': str(report.record.resolve()),
        'started_at': report.started_at or '',
        'last_record_type': report.last_record_type or '',
        'last_record_timestamp': report.last_record_timestamp or '',
        'parse_errors': report.parse_errors,
        'open_files': report.open_files,
        'missing_files': report.missing_files,
        'sources': [source.model_dump() for source in report.sources],
        'tracks': [track.model_dump(exclude_none=True) for track in report.tracks],
    }
    if report.disk is not None:
        values['disk'] = report.disk.model_dump(exclude_none=True)
    return tomlkit.dumps(values)
