import json
import sys
from pathlib import Path

from pydantic import BaseModel, Field
from ufor.recording import AudioStream, EventStream

from ..base.errors import RecsError
from ..recording import legacy
from ..recording.read import read_recording
from . import session_record

RECORD_GLOB = 'recording.toml'


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
    state: str
    unresolved_audio_files: int = 0
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
    record_path = path / RECORD_GLOB
    if not record_path.is_file():
        return None
    try:
        document = read_recording(record_path)
    except RecsError:
        return None
    body = document.body
    assets = {a.name: a for a in document.assets}
    audio = [s for s in body.streams if isinstance(s, AudioStream)]
    events = [s for s in body.streams if isinstance(s, EventStream)]
    audio_assets = {
        f.asset for s in audio for f in [*s.fragments, *s.unmapped_fragments]
    }
    event_assets = {f.asset for s in events for f in s.fragments}
    media = audio_assets | event_assets
    try:
        journal = None
        if body.journal is not None:
            asset = assets[body.journal]
            journal = (
                legacy.read(path / asset.path)
                if asset.encoding == 'recs-session-v3'
                else session_record.read(path / asset.path)
            )
    except OSError as error:
        journal = None
        warnings = [f'Cannot read capture diagnostics: {error}']
    else:
        warnings = journal.warnings + journal.errors if journal else []
    unresolved = sum(len(s.unmapped_fragments) for s in audio)
    if unresolved:
        warnings.append(f'{unresolved} audio files have unresolved timeline placement')
    if body.unfinished_files:
        warnings.append(f'{len(body.unfinished_files)} files are unfinished')
    return SessionSummary(
        path=path.as_posix(),
        started_at=body.started_at or 'unknown',
        ended_at=body.ended_at,
        duration=body.observed_duration_seconds,
        output_directories=sorted(
            {(path / assets[a].path).parent.as_posix() for a in media}
        ),
        devices=sorted({s.source_name or s.source_id for s in audio}),
        tracks=sorted(
            {f'{s.source_name or s.source_id}:{s.track_name or s.name}' for s in audio}
        ),
        midi_ports=sorted(
            {
                s.source_id.removeprefix('midi:')
                for s in events
                if (s.event_kind == 'midi' or s.event_schema == 'midi')
            }
        ),
        files=len(media),
        audio_files=len(audio_assets),
        midi_files=len(
            {
                f.asset
                for s in events
                if (s.event_kind == 'midi' or s.event_schema == 'midi')
                for f in s.fragments
            }
        ),
        midi_messages=sum(
            f.event_count
            for s in events
            if (s.event_kind == 'midi' or s.event_schema == 'midi')
            for f in s.fragments
        ),
        total_bytes=sum(assets[a].byte_length for a in media),
        warnings=warnings,
        state=body.state,
        unresolved_audio_files=unresolved,
        disk_events=sum(e.type.startswith('disk_') for e in journal.events)
        if journal
        else 0,
        markers=sum(e.type in {'key_pressed', 'mark'} for e in journal.events)
        if journal
        else 0,
        continued_from=body.continued_from,
        continued_at=body.continued_at,
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
    print(f'state: {value.state}')
    print(f'unresolved_audio_files: {value.unresolved_audio_files}')
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
