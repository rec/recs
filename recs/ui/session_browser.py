import json
import sys
from pathlib import Path

from pydantic import BaseModel, Field

from . import session_manifest

MANIFEST_NAME = 'recs-session.jsonl'


class SessionSummary(BaseModel):
    path: str
    started_at: str
    ended_at: str | None
    duration: float | None
    output_directories: list[str] = Field(default_factory=list)
    devices: list[str] = Field(default_factory=list)
    tracks: list[str] = Field(default_factory=list)
    files: int
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
    if root.name == MANIFEST_NAME:
        manifests = [root]
    else:
        manifests = sorted(root.glob(f'**/{MANIFEST_NAME}'))
    return [summary for path in manifests if (summary := summarize(path))]


def summarize(path: Path) -> SessionSummary | None:
    try:
        manifest = session_manifest.read(path)
    except OSError:
        return None
    if not manifest.started_at:
        return None
    finished = [f for f in manifest.files if f.type == 'file_finished']
    paths = [_file_path(path, f.path) for f in finished]
    return SessionSummary(
        path=path.as_posix(),
        started_at=manifest.started_at,
        ended_at=manifest.ended_at,
        duration=manifest.duration,
        output_directories=sorted({p.parent.as_posix() for p in paths}),
        devices=sorted({f.source for f in finished if f.source}),
        tracks=sorted(
            {
                f'{f.source or "unknown"}:{f.track}'
                for f in finished
                if f.track is not None
            }
        ),
        files=len(finished),
        total_bytes=sum(p.stat().st_size for p in paths if p.exists()),
        warnings=manifest.warnings + manifest.errors,
        disk_events=sum(1 for e in manifest.events if e.type.startswith('disk_')),
        markers=sum(1 for e in manifest.events if e.type in {'key_pressed', 'mark'}),
        continued_from=manifest.continued_from,
        continued_at=[
            e.continued_at
            for e in manifest.events
            if e.type == 'disk_switch_continued_at' and e.continued_at is not None
        ],
    )


def _show(argv: list[str]) -> int:
    json_output = False
    if '--json' in argv:
        json_output = True
        argv = [arg for arg in argv if arg != '--json']
    if len(argv) != 1:
        print('Usage: recs session show PATH [--json]', file=sys.stderr)
        return 2
    if (value := summarize(Path(argv[0]))) is None:
        print(f'{argv[0]}: not a readable recs manifest', file=sys.stderr)
        return 1
    if json_output:
        print(value.model_dump_json(indent=2))
    else:
        _print_summary(value)
    return 0


def _print_summaries(summaries: list[SessionSummary]) -> None:
    for value in summaries:
        print(
            f'{value.started_at}  files={value.files}  '
            f'bytes={value.total_bytes}  {value.path}'
        )


def _print_summary(value: SessionSummary) -> None:
    print(f'path: {value.path}')
    print(f'started_at: {value.started_at}')
    print(f'ended_at: {value.ended_at or ""}')
    print(f'duration: {value.duration if value.duration is not None else ""}')
    print(f'files: {value.files}')
    print(f'total_bytes: {value.total_bytes}')
    print(f'devices: {", ".join(value.devices)}')
    print(f'tracks: {", ".join(value.tracks)}')
    print(f'output_directories: {", ".join(value.output_directories)}')
    print(f'warnings: {len(value.warnings)}')
    print(f'disk_events: {value.disk_events}')
    print(f'markers: {value.markers}')
    if value.continued_from:
        print(f'continued_from: {value.continued_from}')
    for path in value.continued_at:
        print(f'continued_at: {path}')


def _file_path(manifest_path: Path, path: str) -> Path:
    result = Path(path)
    if result.is_absolute():
        return result
    return manifest_path.parent / result
