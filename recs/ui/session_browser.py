import json
import sys
from pathlib import Path

from pydantic import BaseModel, Field

from . import session_record

RECORD_GLOB = 'session-record.jsonl'


class SessionSummary(BaseModel):
    path: str
    started_at: str
    ended_at: str | None
    duration: float | None
    output_directories: list[str] = Field(default_factory=list)
    devices: list[str] = Field(default_factory=list)
    tracks: list[str] = Field(default_factory=list)
    midi_ports: list[str] = Field(default_factory=list)
    files: int
    audio_files: int = 0
    midi_files: int = 0
    midi_messages: int = 0
    total_bytes: int
    warnings: list[str] = Field(default_factory=list)
    disk_events: int = 0
    markers: int = 0
    continued_from: str | None = None
    continued_at: list[str] = Field(default_factory=list)


def main(argv: list[str]) -> int:
    if argv and argv[0] == 'show':
        return _show(argv[1:])
    json_output = False
    if '--json' in argv:
        json_output = True
        argv = [arg for arg in argv if arg != '--json']
    root = Path(argv[0]) if argv else Path()
    summaries = list(scan(root))
    if json_output:
        print(json.dumps([s.model_dump(mode='json') for s in summaries], indent=2))
    else:
        _print_summaries(summaries)
    return 0


def scan(root: Path) -> list[SessionSummary]:
    if root.match(RECORD_GLOB):
        directories = [root.parent]
    elif any(root.glob(RECORD_GLOB)):
        directories = [root]
    else:
        directories = sorted({path.parent for path in root.glob(f'**/{RECORD_GLOB}')})
    return [summary for path in directories if (summary := summarize(path))]


def summarize(path: Path) -> SessionSummary | None:
    if path.match(RECORD_GLOB):
        path = path.parent
    records = _records(path)
    if not records:
        return None
    primary = records[0]
    finished = [
        file
        for record_path, record in records
        for file in record.files
        if file.type == 'file_finished'
    ]
    audio = [f for f in finished if f.media_type == 'audio']
    midi = [f for f in finished if f.media_type == 'midi']
    paths = [
        _file_path(record_path, file.path)
        for record_path, record in records
        for file in record.files
        if file.type == 'file_finished'
    ]
    return SessionSummary(
        path=path.as_posix(),
        started_at=primary[1].started_at,
        ended_at=primary[1].ended_at,
        duration=primary[1].duration_seconds,
        output_directories=sorted({p.parent.as_posix() for p in paths}),
        devices=sorted({f.source for f in audio if f.source}),
        tracks=sorted(
            {f'{f.source or "unknown"}:{f.track}' for f in audio if f.track is not None}
        ),
        midi_ports=_midi_ports(midi),
        files=len(finished),
        audio_files=len(audio),
        midi_files=len(midi),
        midi_messages=sum(f.quantity_count or 0 for f in midi),
        total_bytes=sum(p.stat().st_size for p in paths if p.exists()),
        warnings=primary[1].warnings + primary[1].errors,
        disk_events=sum(1 for e in primary[1].events if e.type.startswith('disk_')),
        markers=sum(
            1 for event in primary[1].events if event.type in {'key_pressed', 'mark'}
        ),
        continued_from=primary[1].continued_from,
        continued_at=[
            event.continued_at
            for event in primary[1].events
            if event.type == 'disk_switch_continued_at'
            and event.continued_at is not None
        ],
    )


def _records(path: Path) -> list[tuple[Path, session_record.SessionRecord]]:
    records: list[tuple[Path, session_record.SessionRecord]] = []
    for record_path in sorted(path.glob(RECORD_GLOB)):
        try:
            record = session_record.read(record_path)
        except OSError:
            continue
        if record.started_at:
            records.append((record_path, record))
    return records


def _midi_ports(files: list[session_record.FileEntry]) -> list[str]:
    names: set[str] = set()
    for file in files:
        if file.midi_port is not None:
            names.add(file.midi_port)
        elif file.source is not None:
            names.add(file.source)
    return sorted(names)


def _show(argv: list[str]) -> int:
    json_output = False
    if '--json' in argv:
        json_output = True
        argv = [arg for arg in argv if arg != '--json']
    if len(argv) != 1:
        print('Usage: recs session show PATH [--json]', file=sys.stderr)
        return 2
    if (value := summarize(Path(argv[0]))) is None:
        print(f'{argv[0]}: not a readable recs record', file=sys.stderr)
        return 1
    if json_output:
        print(value.model_dump_json(indent=2))
    else:
        _print_summary(value)
    return 0


def _print_summaries(summaries: list[SessionSummary]) -> None:
    for value in summaries:
        print(
            f'{value.started_at}  audio={value.audio_files}  '
            f'midi={value.midi_files}  '
            f'bytes={value.total_bytes}  {value.path}'
        )


def _print_summary(value: SessionSummary) -> None:
    print(f'path: {value.path}')
    print(f'started_at: {value.started_at}')
    print(f'ended_at: {value.ended_at or ""}')
    print(f'duration: {value.duration if value.duration is not None else ""}')
    print(f'files: {value.files}')
    print(f'audio_files: {value.audio_files}')
    print(f'midi_files: {value.midi_files}')
    print(f'midi_messages: {value.midi_messages}')
    print(f'total_bytes: {value.total_bytes}')
    print(f'devices: {", ".join(value.devices)}')
    print(f'tracks: {", ".join(value.tracks)}')
    print(f'midi_ports: {", ".join(value.midi_ports)}')
    print(f'output_directories: {", ".join(value.output_directories)}')
    print(f'warnings: {len(value.warnings)}')
    print(f'disk_events: {value.disk_events}')
    print(f'markers: {value.markers}')
    if value.continued_from:
        print(f'continued_from: {value.continued_from}')
    for path in value.continued_at:
        print(f'continued_at: {path}')


def _file_path(record_path: Path, path: str) -> Path:
    return record_path.parent / Path(path)
