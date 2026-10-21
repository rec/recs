"""Correct capture wall clocks and timestamp-based recording paths."""

import hashlib
import json
import os
import re
from datetime import datetime, timedelta
from functools import partial
from pathlib import Path
from tempfile import mkdtemp
from typing import Annotated

import tyro
from pydantic import BaseModel, Field
from ufor.codec import score_toml
from ufor.recording import RecordingScore

from ..base.errors import RecsError
from . import session_record
from .read import read_recording


class OffsetCli(BaseModel, frozen=True):
    """Shift stopped sessions recursively, including journals and recording documents.

    Seconds are added to recorded wall times. Positive values move recordings
    later; negative values move them earlier. Media bytes and native timing stay
    unchanged. Stop recording before using this command.
    """

    directory: Annotated[Path, tyro.conf.Positional]
    seconds: Annotated[float, tyro.conf.Positional] = Field(allow_inf_nan=False)
    """Signed offset in seconds, for example 3600 or -3600."""


class SessionChange(BaseModel, frozen=True):
    source: Path
    destination: Path
    paths: dict[Path, Path]
    contents: dict[Path, str]


def main(argv: list[str]) -> int:
    cfg = tyro.cli(OffsetCli, args=argv, prog='recs offset')
    for source, destination in offset_sessions(cfg.directory, cfg.seconds):
        print(f'{source} -> {destination}')
    return 0


def offset_sessions(directory: Path, seconds: float) -> list[tuple[Path, Path]]:
    """Plan every change before moving or rewriting any session."""
    cfg = OffsetCli(directory=directory, seconds=seconds)
    root = cfg.directory.resolve()
    if not root.is_dir():
        raise RecsError(f'Not a directory: {root}')
    delta = timedelta(seconds=cfg.seconds)
    sessions = sorted(
        {
            p.parent
            for n in ('session-record.jsonl', 'recording.toml')
            for p in root.rglob(n)
        }
    )
    if not sessions:
        raise RecsError(f'No sessions found in {root}')
    if not delta:
        return [(p, p) for p in sessions]
    destinations = {p: _session_destination(p, delta) for p in sessions}
    for source, destination in destinations.items():
        if any(source.is_relative_to(p) for p in sessions if p != source):
            raise RecsError(f'Nested session directory: {source}')
        if (
            destination != source
            and destination.exists()
            and destination not in sessions
        ):
            raise RecsError(f'Destination already exists: {destination}')
    if len(set(destinations.values())) != len(sessions):
        raise RecsError('Multiple sessions have the same destination')
    changes = [_prepare(p, destinations, delta) for p in sessions]
    # Keep staging on failure so an I/O error cannot delete original media.
    staging = Path(
        mkdtemp(prefix='recs-offset-', dir=root.parent if root in sessions else root)
    )
    try:
        for i, change in enumerate(changes):
            for j, content in enumerate(change.contents.values()):
                (staging / f'{i}-{j}.replacement').write_text(content)
        for i, change in enumerate(changes):
            change.source.rename(staging / str(i))
        for i, change in enumerate(changes):
            staged = staging / str(i)
            renamed = staging / f'{i}-renamed'
            renamed.mkdir()
            for relative in change.paths.values():
                (renamed / relative).parent.mkdir(parents=True, exist_ok=True)
            for old, new in change.paths.items():
                path = staged / old
                if path.is_dir():
                    (renamed / new).mkdir(parents=True, exist_ok=True)
                else:
                    path.rename(renamed / new)
            for old in sorted(change.paths, key=lambda p: len(p.parts), reverse=True):
                if (staged / old).is_dir():
                    (staged / old).rmdir()
            staged.rmdir()
            for j, relative in enumerate(change.contents):
                (staging / f'{i}-{j}.replacement').replace(renamed / relative)
        for i, change in enumerate(changes):
            change.destination.parent.mkdir(parents=True, exist_ok=True)
            (staging / f'{i}-renamed').rename(change.destination)
        staging.rmdir()
    except OSError as error:
        raise RecsError(
            f'Offset interrupted; retained files in {staging}: {error}'
        ) from error
    return [(c.source, c.destination) for c in changes]


def _prepare(
    source: Path, destinations: dict[Path, Path], delta: timedelta
) -> SessionChange:
    paths = {
        p.relative_to(source): Path(
            _shift_name(p.relative_to(source).as_posix(), delta)
        )
        for p in source.rglob('*')
    }
    if any(p.is_symlink() for p in source.rglob('*')):
        raise RecsError(f'Session contains symbolic links: {source}')
    if len(set(paths.values())) != len(paths):
        raise RecsError(f'Filename collision in {source}')
    contents: dict[Path, str] = {}
    journal = source / 'session-record.jsonl'
    if journal.exists():
        entries, errors = session_record.read_entries(journal)
        if errors:
            raise RecsError('; '.join(errors))
        if not entries or not isinstance(entries[0], session_record.SessionHeader):
            raise RecsError(f'Missing session header: {journal}')
        records = [e.model_dump(mode='json', exclude_none=True) for e in entries]
        for record in records:
            _shift_record(record, source, destinations, delta)
        contents[Path('session-record.jsonl')] = ''.join(
            json.dumps(r, ensure_ascii=False) + '\n' for r in records
        )
    document_path = source / 'recording.toml'
    if document_path.exists():
        document = read_recording(document_path)
        data = document.model_dump(mode='json', exclude_none=True)
        _shift_record(data, source, destinations, delta)
        for asset in data['assets']:
            if asset['location']['kind'] != 'relative_file':
                raise RecsError(f'Expected session-local asset: {document_path}')
            if asset['name'] == document.body.journal:
                content = contents.get(Path(asset['location']['path']))
                if content is None:
                    raise RecsError(f'Missing capture journal: {document_path}')
                payload = content.encode()
                asset['content'] = {
                    'byte_length': len(payload),
                    'sha256': hashlib.sha256(payload).hexdigest(),
                }
        document = RecordingScore.model_validate(data)
        contents[Path('recording.toml')] = score_toml(document)
    return SessionChange(
        source=source, destination=destinations[source], paths=paths, contents=contents
    )


def _shift_record(
    data: object,
    source: Path,
    destinations: dict[Path, Path],
    delta: timedelta,
) -> None:
    if isinstance(data, list):
        for item in data:
            _shift_record(item, source, destinations, delta)
    elif isinstance(data, dict):
        for key, value in data.items():
            if key in {'metadata', 'application', 'value'}:
                continue
            if key in TIME_FIELDS and isinstance(value, str):
                shifted = datetime.fromisoformat(value) + delta
                data[key] = shifted.isoformat().replace('+00:00', 'Z')
            elif key in PATH_FIELDS and isinstance(value, str):
                data[key] = _shift_reference(value, source, destinations, delta)
            elif key == 'continued_at' and isinstance(value, list):
                data[key] = [
                    _shift_reference(v, source, destinations, delta) for v in value
                ]
            else:
                _shift_record(value, source, destinations, delta)
        if data.get('timebase') == 'wall' and isinstance(data.get('tick'), int):
            data['tick'] += (
                delta.days * 86400 + delta.seconds
            ) * 1_000_000_000 + delta.microseconds * 1000


def _shift_reference(
    value: str, source: Path, destinations: dict[Path, Path], delta: timedelta
) -> str:
    path = Path(value)
    absolute = (source / path).resolve()
    for old, new in destinations.items():
        if absolute.is_relative_to(old):
            relative = absolute.relative_to(old)
            target = new / _shift_name(relative.as_posix(), delta)
            return (
                str(target)
                if path.is_absolute()
                else Path(os.path.relpath(target, destinations[source])).as_posix()
            )
    # External continuation links still need rebasing when this session moves.
    return (
        value
        if path.is_absolute()
        else Path(os.path.relpath(absolute, destinations[source])).as_posix()
    )


def _session_destination(path: Path, delta: timedelta) -> Path:
    if not SESSION_SUFFIX.search(path.as_posix()):
        return path.with_name(_shift_name(path.name, delta))
    return Path(
        SESSION_SUFFIX.sub(
            lambda m: _shift_match(m, delta, '%Y/%m/%d/%H-%M-%S'), path.as_posix()
        )
    )


def _shift_name(value: str, delta: timedelta) -> str:
    for pattern, format in NAME_FORMATS:
        value = pattern.sub(partial(_shift_match, delta=delta, format=format), value)
    return value


def _shift_match(match: re.Match[str], delta: timedelta, format: str) -> str:
    return (datetime.strptime(match[0], format) + delta).strftime(format)


TIME_FIELDS = {'started_at', 'ended_at', 'timestamp', 'observed_at', 'first_timestamp'}
PATH_FIELDS = {
    'path',
    'from_path',
    'to_path',
    'current_path',
    'continued_from',
    'continued_at',
}
SESSION_SUFFIX = re.compile(r'\d{4}/\d{2}/\d{2}/\d{2}-\d{2}-\d{2}(?=(?:_\d+)?$)')
NAME_FORMATS = [
    (re.compile(r'(?<!\d)\d{8}-\d{6}(?!\d)'), '%Y%m%d-%H%M%S'),
    (re.compile(r'(?<!\d)\d{6}_\d{8}(?!\d)'), '%H%M%S_%Y%m%d'),
    (
        re.compile(r'(?<!\d)\d{4}/\d{2}/\d{2}/\d{2}-\d{2}-\d{2}(?!\d)'),
        '%Y/%m/%d/%H-%M-%S',
    ),
]
