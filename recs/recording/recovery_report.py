import hashlib
import os
import sys
from pathlib import Path
from typing import Annotated

import tomlkit
import tyro
from pydantic import BaseModel, Field
from reccy.runtime import logging

from ..base.errors import RecsError
from . import recording_paths, session_record
from .read import read_recording

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
    finalization_error: str | None = None


class Fingerprint(BaseModel, frozen=True):
    exists: bool
    device: int | None = None
    inode: int | None = None
    size: int | None = None
    modified_ns: int | None = None


class RecoveryRoot(BaseModel, frozen=True):
    path: str
    device: int
    inode: int


class RecoveryCandidate(BaseModel, frozen=True):
    record: str
    root: str
    journal: Fingerprint
    media: dict[str, Fingerprint] = Field(default_factory=dict)
    report_digest: str | None = None
    announced_digest: str | None = None


class RecoveryWorklist(BaseModel, frozen=True):
    roots: list[RecoveryRoot] = Field(default_factory=list)
    candidates: dict[str, RecoveryCandidate] = Field(default_factory=dict)


class RecoverScanCli(BaseModel, frozen=True):
    """Discover unfinished session records below ROOT once."""

    root: Annotated[Path, tyro.conf.Positional]


def main_scan(argv: list[str]) -> int:
    command = tyro.cli(RecoverScanCli, args=argv, prog='recs session recover-scan')
    for path in report_unfinished_sessions(command.root, discover=True):
        print(path)
    return 0


def report_unfinished_sessions(
    root: Path, *, discover: bool | None = None
) -> list[Path]:
    if not root.exists():
        return []
    root_path = str(root.resolve())
    identity = _fingerprint(root)
    if identity.device is None or identity.inode is None:
        return []
    worklist = _load_worklist()
    known = RecoveryRoot(path=root_path, device=identity.device, inode=identity.inode)
    if discover is None:
        discover = known not in worklist.roots
    candidates = dict(worklist.candidates)
    roots = [value for value in worklist.roots if value.path != root_path]
    roots.append(known)
    if discover:
        for record_path in sorted(root.rglob('session-record.jsonl')):
            key = str(record_path.resolve())
            candidates.setdefault(
                key,
                RecoveryCandidate(
                    record=key,
                    root=root_path,
                    journal=_fingerprint(record_path),
                ),
            )
    reports: list[Path] = []
    for key, candidate in list(candidates.items()):
        if candidate.root != root_path:
            continue
        record_path = Path(candidate.record)
        current = _fingerprint(record_path)
        if not current.exists:
            candidates[key] = candidate.model_copy(update={'journal': current})
            continue
        report_path = record_path.parent / REPORT_FILE
        report_changed = _digest_path(report_path) != candidate.report_digest
        media_changed = any(
            _fingerprint(record_path.parent / path) != fingerprint
            for path, fingerprint in candidate.media.items()
        )
        if (
            current == candidate.journal
            and not media_changed
            and not report_changed
            and candidate.report_digest is not None
        ):
            continue
        try:
            report = recovery_report(record_path)
        except OSError as e:
            LOGGER.error('Cannot inspect record %s: %s', record_path, e)
            continue
        if report is None:
            if _digest_path(report_path) == candidate.report_digest:
                report_path.unlink(missing_ok=True)
            del candidates[key]
            continue
        text = _toml(report)
        digest = _digest(text)
        try:
            if _digest_path(report_path) != digest:
                recording_paths.write_text_atomically(report_path, text)
        except OSError as e:
            LOGGER.error('Cannot write recovery report %s: %s', report_path, e)
            continue
        if candidate.announced_digest != digest:
            LOGGER.error('%s: see %s', _summary(report), report_path.resolve())
            reports.append(report_path)
        candidates[key] = RecoveryCandidate(
            record=key,
            root=root_path,
            journal=current,
            media={
                path: _fingerprint(record_path.parent / path)
                for path in report.open_files
            },
            report_digest=digest,
            announced_digest=digest,
        )
    _save_worklist(RecoveryWorklist(roots=roots, candidates=candidates))
    return reports


def register_unfinished_session(root: Path, record: Path) -> None:
    worklist = _load_worklist()
    key = str(record.resolve())
    candidates = dict(worklist.candidates)
    candidates.setdefault(
        key,
        RecoveryCandidate(
            record=key,
            root=str(root.resolve()),
            journal=_fingerprint(record),
        ),
    )
    _save_worklist(worklist.model_copy(update={'candidates': candidates}))


def clear_finished_session(record: Path) -> None:
    worklist = _load_worklist()
    key = str(record.resolve())
    candidate = worklist.candidates.get(key)
    if candidate is None:
        return
    try:
        report = recovery_report(record)
    except OSError:
        return
    if report is not None:
        return
    report_path = record.parent / REPORT_FILE
    if _digest_path(report_path) == candidate.report_digest:
        report_path.unlink(missing_ok=True)
    candidates = dict(worklist.candidates)
    del candidates[key]
    _save_worklist(worklist.model_copy(update={'candidates': candidates}))


def worklist_path() -> Path:
    if sys.platform == 'win32':
        appdata = Path(os.environ.get('APPDATA', Path.home() / 'AppData/Roaming'))
        return appdata / 'recs/recovery-worklist.json'
    return Path.home() / '.local/state/recs/recovery-worklist.json'


def _load_worklist() -> RecoveryWorklist:
    path = worklist_path()
    if not path.exists():
        return RecoveryWorklist()
    try:
        return RecoveryWorklist.model_validate_json(path.read_text())
    except (OSError, ValueError):
        LOGGER.warning('Cannot read recovery worklist %s; rediscovering sessions', path)
        return RecoveryWorklist()


def _save_worklist(worklist: RecoveryWorklist) -> None:
    path = worklist_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        recording_paths.write_text_atomically(path, worklist.model_dump_json())
    except OSError as error:
        LOGGER.warning('Cannot save recovery worklist %s: %s', path, error)


def _fingerprint(path: Path) -> Fingerprint:
    try:
        status = path.stat()
    except OSError:
        return Fingerprint(exists=False)
    return Fingerprint(
        exists=True,
        device=status.st_dev,
        inode=status.st_ino,
        size=status.st_size,
        modified_ns=status.st_mtime_ns,
    )


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _digest_path(path: Path) -> str | None:
    try:
        return _digest(path.read_text())
    except OSError:
        return None


def recovery_report(path: Path) -> RecoveryReport | None:
    records, errors = session_record.read_entries(path)
    finalization_error = None
    if any(isinstance(record, session_record.SessionFooter) for record in records):
        try:
            document = read_recording(path.with_name('recording.toml'))
        except RecsError as error:
            finalization_error = str(error)
        else:
            if document.body.state == 'sealed':
                return None
            finalization_error = 'Recording document remains open'
    header = next(
        (
            record
            for record in records
            if isinstance(record, session_record.SessionHeader)
        ),
        None,
    )
    files = [
        record
        for record in records
        if isinstance(
            record, session_record.AudioFileRecord | session_record.EventFileRecord
        )
    ]
    started = {record.path: record for record in files if record.type == 'file_started'}
    finished = {
        record.path
        for record in files
        if record.type in {'file_finished', 'file_discarded'}
    }
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
        finalization_error=finalization_error,
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
    files: list[session_record.AudioFileRecord | session_record.EventFileRecord],
    open_files: list[str],
    missing_files: list[str],
) -> list[TrackReport]:
    reports: dict[tuple[str, str | None, tuple[int, ...], str | None], TrackReport] = {}
    for file in files:
        audio = file if isinstance(file, session_record.AudioFileRecord) else None
        midi_port = file.source if file.media_type == 'midi' else None
        key = (
            file.media_type,
            file.source,
            tuple(audio.source_channels or []) if audio else (),
            midi_port,
        )
        current = reports.get(
            key,
            TrackReport(
                media_type=file.media_type,
                source=file.source,
                track_name=audio.track_name if audio else None,
                source_channels=audio.source_channels if audio else None,
                midi_port=midi_port,
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
    if report.finalization_error:
        counts.append('recording finalization incomplete')
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
    if report.finalization_error is not None:
        values['finalization_error'] = report.finalization_error
    return tomlkit.dumps(values)
