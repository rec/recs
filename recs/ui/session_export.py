import os
import shutil
import uuid
from pathlib import Path
from typing import Annotated

import tomlkit
import tyro
from pydantic import BaseModel

from recs.base.errors import RecsError
from recs.misc import legal_filename

from . import session_record


class ExportCli(BaseModel, frozen=True):
    record: Annotated[Path, tyro.conf.Positional]

    destination: Annotated[Path, tyro.conf.Positional]


def export(record: Path, destination: Path) -> Path:
    record = record.resolve()
    destination = destination.resolve()
    if destination.exists():
        raise RecsError(f'Export destination already exists: {destination}')

    records = _records(record)
    temporary = destination.with_name(
        f'.{destination.name}.recs-export-{uuid.uuid4().hex}'
    )
    temporary.mkdir(parents=True)
    try:
        destinations = {
            path: temporary
            / 'sessions'
            / f'{i:03d}-{legal_filename.legal_filename(path.parent.name)}'
            / 'session-record.jsonl'
            for i, path in enumerate(records)
        }
        file_count, total_bytes = _copy_records(records, destinations)
        summary = {
            'version': 1,
            'source_record': str(record),
            'record_count': len(records),
            'file_count': file_count,
            'total_bytes': total_bytes,
            'records': [
                {
                    'source': str(path),
                    'path': destinations[path].relative_to(temporary).as_posix(),
                }
                for path in records
            ],
        }
        (temporary / 'export-summary.toml').write_text(tomlkit.dumps(summary))
        temporary.replace(destination)
    except (OSError, RecsError):
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return destination


def main(argv: list[str] | None = None) -> int:
    command = tyro.cli(
        ExportCli,
        args=argv,
        prog='recs session export',
        description='Copy a complete Recs session into a portable directory.',
    )
    print(export(command.record, command.destination))
    return 0


def _records(first: Path) -> list[Path]:
    pending = [first]
    result: list[Path] = []
    seen: set[Path] = set()
    while pending:
        path = pending.pop(0).resolve()
        if path in seen:
            continue
        if not path.is_file():
            raise RecsError(f'Linked session record does not exist: {path}')
        seen.add(path)
        result.append(path)
        entries, errors = session_record.read_entries(path)
        if errors:
            raise RecsError('\n'.join(errors))
        pending.extend(
            linked
            for value in _record_links(entries)
            if (linked := (path.parent / value).resolve()) not in seen
        )
    return result


def _copy_records(
    records: list[Path], destinations: dict[Path, Path]
) -> tuple[int, int]:
    copied: set[Path] = set()
    total_bytes = 0
    for record in records:
        entries, errors = session_record.read_entries(record)
        if errors:
            raise RecsError('\n'.join(errors))
        output = destinations[record]
        output.parent.mkdir(parents=True)
        rewritten: list[str] = []
        for entry in entries:
            if isinstance(entry, session_record.FileRecord):
                source = _media_path(record, entry.path)
                target = output.parent / entry.path
                if source not in copied:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, target)
                    if source.stat().st_size != target.stat().st_size:
                        raise RecsError(f'Exported file size differs: {source}')
                    copied.add(source)
                    total_bytes += source.stat().st_size
            rewritten.append(
                _rewrite_links(entry, record, output, destinations).model_dump_json(
                    exclude_none=True
                )
            )
        output.write_text('\n'.join(rewritten) + '\n')
    return len(copied), total_bytes


def _record_links(entries: list[session_record.Record]) -> list[str]:
    links: list[str] = []
    for entry in entries:
        if isinstance(entry, session_record.SessionHeader) and entry.continued_from:
            links.append(entry.continued_from)
        elif (
            isinstance(entry, session_record.EventRecord)
            and entry.type in {'disk_switch_continued_at', 'session_continued_at'}
            and entry.continued_at
        ):
            links.append(entry.continued_at)
    return links


def _rewrite_links(
    entry: session_record.Record,
    source_record: Path,
    output_record: Path,
    destinations: dict[Path, Path],
) -> session_record.Record:
    if isinstance(entry, session_record.SessionHeader) and entry.continued_from:
        return entry.model_copy(
            update={
                'continued_from': _export_link(
                    source_record,
                    entry.continued_from,
                    output_record,
                    destinations,
                )
            }
        )
    if (
        isinstance(entry, session_record.EventRecord)
        and entry.type in {'disk_switch_continued_at', 'session_continued_at'}
        and entry.continued_at
    ):
        return entry.model_copy(
            update={
                'continued_at': _export_link(
                    source_record,
                    entry.continued_at,
                    output_record,
                    destinations,
                )
            }
        )
    return entry


def _export_link(
    source_record: Path,
    link: str,
    output_record: Path,
    destinations: dict[Path, Path],
) -> str:
    linked = (source_record.parent / link).resolve()
    if (target := destinations.get(linked)) is None:
        raise RecsError(f'Linked session record was not exported: {linked}')
    return Path(os.path.relpath(target, output_record.parent)).as_posix()


def _media_path(record: Path, value: str) -> Path:
    path = Path(value)
    if path.is_absolute():
        raise RecsError(f'{record}: media path must be relative: {value}')
    resolved = (record.parent / path).resolve()
    if not resolved.is_relative_to(record.parent.resolve()):
        raise RecsError(f'{record}: media path escapes session: {value}')
    if not resolved.is_file():
        raise RecsError(f'{record}: missing media file: {value}')
    return resolved
