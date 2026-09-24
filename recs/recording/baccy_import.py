"""Import the known recordings staged for baccy without moving their media."""

import hashlib
import re
import shlex
import struct
import uuid
from collections.abc import Iterable, Mapping
from datetime import datetime
from pathlib import Path
from time import mktime
from typing import Annotated

import soundfile
import tyro
from pydantic import BaseModel
from ufor.assets import Asset, ContentIdentity, RelativeFileLocation
from ufor.codec import parse_score, score_toml
from ufor.recording import AudioFragment, AudioStream, Recording, RecordingScore
from ufor.streams import AudioType
from ufor.time import Rate, Timebase

from recs.base.errors import RecsError
from recs.recording import recording_paths, session_record
from recs.recording.files import asset_path
from recs.recording.legacy_finalize import prepare_legacy_recording


class ImportConfig(BaseModel, frozen=True):
    source_root: Annotated[Path, tyro.conf.Positional]
    destination_root: Annotated[Path, tyro.conf.Positional]


class ImportedSession(BaseModel, frozen=True):
    project_name: str
    source_paths: list[Path]
    session_directory: Path
    commands: list[str]


class AudioInput(BaseModel, frozen=True):
    path: Path
    source_name: str
    track_name: str
    source_channels: list[int]
    timestamp: float
    project_name: str


_DATE_DIRECTORY = re.compile(r'^\d{4}-\d{2}-\d{2}$')
_LIVETRAK_DIRECTORY = re.compile(r'^(\d{2})(\d{2})(\d{2})_(\d{2})(\d{2})(\d{2})$')
_PAIR = re.compile(r'^(\d+)(?:-(\d+))? \+ (\d{6})$')
_TIME_DIRECTORY = re.compile(r'^(\d{2})-(\d{2})-(\d{2})(?: copy)?$')
_PROJECTS = {'totm', 'oderg in duo'}


def main(argv: list[str] | None = None) -> int:
    config = tyro.cli(ImportConfig, args=argv, prog='import-baccy-recordings')
    for session in import_recordings(config.source_root, config.destination_root):
        for command in session.commands:
            print(command)
    return 0


def import_recordings(
    source_root: Path, destination_root: Path
) -> list[ImportedSession]:
    source_root = source_root.resolve()
    if not source_root.is_dir():
        raise RecsError(f'Import source is not a directory: {source_root}')
    projects = [
        p for p in source_root.iterdir() if p.is_dir() and not p.name.startswith('.')
    ]
    unknown = sorted(p.name for p in projects if p.name not in _PROJECTS)
    if unknown:
        raise RecsError(f'Unknown baccy import projects: {", ".join(unknown)}')
    result: list[ImportedSession] = []
    consumed: set[Path] = set()
    for project in sorted(projects, key=lambda p: p.name):
        for session in _legacy_sessions(project, destination_root):
            result.append(session)
            consumed.update(session.source_paths)
        for session in _livetrak_sessions(project, destination_root):
            result.append(session)
            consumed.update(session.source_paths)
        result.extend(_flow_sessions(project, destination_root, consumed))
    return result


def _legacy_sessions(project: Path, destination_root: Path) -> list[ImportedSession]:
    result: list[ImportedSession] = []
    for journal in sorted(project.rglob('session-record.jsonl')):
        source = journal.parent
        if not (source / 'recording.toml').is_file():
            raise RecsError(f'Legacy session has no recording.toml: {source}')
        timestamp = _timestamp_from_name(source.name)
        destination = _import_destination(destination_root, timestamp, project.name)
        document, _ = prepare_legacy_recording(journal, source.parent)
        original_journal = document.body.journal
        if original_journal is None:
            raise RecsError(f'Legacy session has no journal asset: {source}')
        assets = [
            asset.model_copy(
                update={
                    'location': RelativeFileLocation(
                        path=(
                            'evidence/session-record-v3.jsonl'
                            if asset.name == original_journal
                            else asset_path(asset)
                        )
                    )
                }
            )
            for asset in document.assets
        ]
        document = document.model_copy(
            update={
                'assets': assets,
                'body': document.body.model_copy(update={'project_name': project.name}),
            }
        )
        paths = [journal, source / 'recording.toml']
        paths.extend(
            source / asset_path(a)
            for a in document.assets
            if a.name != original_journal
        )
        result.append(
            _write_legacy_session(
                source_root=project.parent,
                source=source,
                destination=destination,
                document=document,
                timestamp=timestamp,
                paths=paths,
            )
        )
    return result


def _write_legacy_session(
    *,
    source_root: Path,
    source: Path,
    destination: Path,
    document: RecordingScore,
    timestamp: float,
    paths: list[Path],
) -> ImportedSession:
    staging = _staging_directory(destination)
    moves = [
        (source / 'session-record.jsonl', Path('evidence/session-record-v3.jsonl')),
        (source / 'recording.toml', Path('evidence/recording-v3.toml')),
        *[
            (path, path.relative_to(source))
            for path in paths
            if path not in {source / 'session-record.jsonl', source / 'recording.toml'}
        ],
    ]
    metadata: dict[str, object] = {
        'imported': True,
        'relocation_pending': True,
        'source_directory': source.relative_to(source_root).as_posix(),
        'timing_source': 'source_name',
    }
    _write_session_record(staging, timestamp, document.body.project_name, metadata)
    (staging / 'evidence').mkdir()
    for asset in document.assets:
        if asset.name == document.body.journal:
            continue
        (staging / asset_path(asset)).parent.mkdir(parents=True, exist_ok=True)
    _write_score(staging, document)
    staging.rename(destination)
    return ImportedSession(
        project_name=document.body.project_name or '',
        source_paths=sorted(set(paths)),
        session_directory=destination,
        commands=_commands(destination, moves),
    )


def _livetrak_sessions(project: Path, destination_root: Path) -> list[ImportedSession]:
    result: list[ImportedSession] = []
    for directory in sorted(project.rglob('*')):
        if (
            not directory.is_dir()
            or _LIVETRAK_DIRECTORY.fullmatch(directory.name) is None
        ):
            continue
        audio_directory = (
            directory / 'Work' if (directory / 'Work').is_dir() else directory
        )
        files = sorted(p for p in audio_directory.glob('*.WAV') if p.is_file())
        if not files:
            continue
        timestamp = _timestamp_from_livetrak(directory.name)
        audio = [
            _audio_input(
                path,
                project.name,
                timestamp,
                'LiveTrak L-12 master' if path.stem == 'MASTER' else 'LiveTrak L-12',
                path.stem,
                _livetrak_channels(path.stem),
            )
            for path in files
        ]
        evidence = [p for p in [directory / 'PRJDATA.ZDT'] if p.is_file()]
        result.append(
            _write_reconstructed_session(
                source_root=project.parent,
                project_name=project.name,
                timestamp=timestamp,
                audio=audio,
                evidence=evidence,
                destination_root=destination_root,
                grouping_rule='livetrak_project_directory',
            )
        )
    return result


def _flow_sessions(
    project: Path, destination_root: Path, consumed: set[Path]
) -> list[ImportedSession]:
    groups: dict[tuple[str, str], list[AudioInput]] = {}
    for path in sorted(_audio_paths(project)):
        if path in consumed:
            continue
        found = _flow_timestamp(path, project)
        if found is None:
            continue
        date, time = found
        pair = _pair_from_path(path)
        if pair is None:
            continue
        source_name = _flow_source_name(path)
        timestamp = _wav_icrd_timestamp(path) or _timestamp(date, time)
        entry = _audio_input(
            path, project.name, timestamp, source_name, pair[0], pair[1]
        )
        groups.setdefault((date, time), []).append(entry)
    result: list[ImportedSession] = []
    for _, entries in sorted(groups.items()):
        selected = _deduplicate_flow_entries(entries)
        timestamp = min(entry.timestamp for entry in selected)
        result.append(
            _write_reconstructed_session(
                source_root=project.parent,
                project_name=project.name,
                timestamp=timestamp,
                audio=selected,
                evidence=[],
                destination_root=destination_root,
                grouping_rule='flow_8_filename_time',
            )
        )
    return result


def _write_reconstructed_session(
    *,
    source_root: Path,
    project_name: str,
    timestamp: float,
    audio: list[AudioInput],
    evidence: list[Path],
    destination_root: Path,
    grouping_rule: str,
) -> ImportedSession:
    if not audio:
        raise RecsError('Cannot create a session without audio')
    destination = _import_destination(destination_root, timestamp, project_name)
    staging = _staging_directory(destination)
    media = [_media_fact(item) for item in audio]
    metadata: dict[str, object] = {
        'imported': True,
        'relocation_pending': True,
        'grouping_rule': grouping_rule,
        'timing_source': 'source_name',
        'sources': [
            {
                'path': item.path.relative_to(source_root).as_posix(),
                'sha256': fact.sha256,
            }
            for item, fact in zip(audio, media, strict=True)
        ],
        'evidence': [path.relative_to(source_root).as_posix() for path in evidence],
    }
    session_id = str(
        uuid.uuid5(
            uuid.NAMESPACE_URL,
            project_name + ''.join(sorted(fact.sha256 for fact in media)),
        )
    )
    duration = max(fact.frames / fact.sample_rate for fact in media)
    _write_session_record(
        staging,
        timestamp,
        project_name,
        metadata,
        session_id=session_id,
        audio=list(zip(audio, media, strict=True)),
        duration=duration,
    )
    (staging / 'audio').mkdir()
    if evidence:
        (staging / 'evidence').mkdir()
    document = _recording_score(
        staging,
        destination.name,
        project_name,
        session_id,
        timestamp,
        audio,
        media,
        duration,
    )
    _write_score(staging, document)
    staging.rename(destination)
    moves = [(item.path, Path('audio') / _media_name(item)) for item in audio]
    moves.extend((path, Path('evidence') / path.name) for path in evidence)
    return ImportedSession(
        project_name=project_name,
        source_paths=[item.path for item in audio] + evidence,
        session_directory=destination,
        commands=_commands(destination, moves),
    )


class MediaFact(BaseModel, frozen=True):
    frames: int
    sample_rate: int
    channels: int
    format: str
    byte_length: int
    sha256: str


def _media_fact(item: AudioInput) -> MediaFact:
    info = soundfile.info(item.path)
    with item.path.open('rb') as source:
        digest = hashlib.file_digest(source, 'sha256').hexdigest()
    return MediaFact(
        frames=info.frames,
        sample_rate=info.samplerate,
        channels=info.channels,
        format=item.path.suffix.removeprefix('.').lower(),
        byte_length=item.path.stat().st_size,
        sha256=digest,
    )


def _recording_score(
    destination: Path,
    title: str,
    project_name: str,
    session_id: str,
    timestamp: float,
    audio: list[AudioInput],
    media: list[MediaFact],
    duration: float,
) -> RecordingScore:
    journal = destination / 'session-record.jsonl'
    journal_asset = _asset(
        'original-journal', Path('session-record.jsonl'), 'recs-session-v5', journal
    )
    assets = [journal_asset]
    streams: list[AudioStream] = []
    clocks: list[Timebase] = []
    for item, fact in zip(audio, media, strict=True):
        identity = hashlib.sha256(f'{item.path}:{fact.sha256}'.encode()).hexdigest()[
            :16
        ]
        asset = Asset(
            name=f'asset-{identity}',
            location=RelativeFileLocation(
                path=(Path('audio') / _media_name(item)).as_posix()
            ),
            encoding=fact.format,
            content=ContentIdentity(byte_length=fact.byte_length, sha256=fact.sha256),
        )
        assets.append(asset)
        clock = Timebase(
            name=f'clock-{identity}', rate=Rate(numerator=fact.sample_rate)
        )
        clocks.append(clock)
        labels = [f'input-{channel}' for channel in item.source_channels]
        if len(labels) != fact.channels:
            labels = [f'channel-{channel}' for channel in range(1, fact.channels + 1)]
        streams.append(
            AudioStream(
                name=f'stream-{identity}',
                source_id=f'audio:{item.source_name}:{item.track_name}',
                source_name=item.source_name,
                track_name=item.track_name,
                stream=AudioType(timebase=clock.name, channels=labels),
                end=fact.frames,
                fragments=[AudioFragment(asset=asset.name, start=0, count=fact.frames)],
            )
        )
    start = session_record.timestamp_to_json(timestamp)
    return RecordingScore(
        name=session_id,
        title=title,
        assets=assets,
        timebases=clocks,
        body=Recording(
            state='sealed',
            project_name=project_name,
            started_at=start,
            ended_at=session_record.timestamp_to_json(timestamp + duration),
            observed_duration_seconds=duration,
            journal=journal_asset.name,
            streams=streams,
        ),
    )


def _write_session_record(
    destination: Path,
    timestamp: float,
    project_name: str | None,
    metadata: Mapping[str, object],
    *,
    session_id: str | None = None,
    audio: list[tuple[AudioInput, MediaFact]] | None = None,
    duration: float = 0,
) -> None:
    destination.mkdir(parents=True)
    started_at = session_record.timestamp_to_json(timestamp)
    writer = session_record.SessionRecordWriter(
        destination / 'session-record.jsonl',
        started_at=started_at,
        session_id=session_id,
        project_name=project_name,
        metadata=dict(metadata),
    )
    for item, fact in audio or []:
        identity = hashlib.sha256(f'{item.path}:{fact.sha256}'.encode()).hexdigest()[
            :16
        ]
        path = (Path('audio') / _media_name(item)).as_posix()
        clock_id = f'clock-{identity}'
        stream_id = session_record.audio_stream_id(item.source_name, item.track_name)
        writer.write(
            session_record.EventRecord(
                type='source_online',
                timestamp=started_at,
                source=item.source_name,
                clock_id=clock_id,
                channel_count=fact.channels,
                sample_rate=fact.sample_rate,
            )
        )
        writer.write(
            session_record.AudioFileRecord(
                type='file_started',
                clock_id=clock_id,
                timestamp=started_at,
                stream_id=stream_id,
                path=path,
                source_channels=item.source_channels,
                frame_count=0,
            )
        )
        writer.write(
            session_record.AudioFileRecord(
                type='file_finished',
                clock_id=clock_id,
                timestamp=started_at,
                stream_id=stream_id,
                path=path,
                source_channels=item.source_channels,
                frame_count=fact.frames,
                quantity_count=fact.frames,
                audio_spans=[
                    session_record.AudioSpan(asset_start=0, start=0, count=fact.frames)
                ],
            )
        )
    writer.write(
        session_record.SessionFooter(
            ended_at=session_record.timestamp_to_json(timestamp + duration),
            duration_seconds=duration,
        )
    )
    writer.close()


def _write_score(destination: Path, document: RecordingScore) -> None:
    path = destination / 'recording.toml'
    with path.open('x') as target:
        target.write(score_toml(document))
    if parse_score(path.read_text()) != document:
        raise RecsError(f'Written recording differs from source: {path}')


def _staging_directory(destination: Path) -> Path:
    if destination.exists():
        raise RecsError(f'Import destination already exists: {destination}')
    staging = destination.with_name(f'.{destination.name}.staging')
    if staging.exists():
        raise RecsError(f'Import staging directory already exists: {staging}')
    return staging


def _import_destination(
    destination_root: Path, timestamp: float, project_name: str
) -> Path:
    destination = (
        destination_root
        / project_name
        / recording_paths.session_day_directory(timestamp)
        / recording_paths.session_directory_name(timestamp)
    )
    if destination.exists():
        raise RecsError(f'Import destination already exists: {destination}')
    return destination


def _commands(
    destination: Path,
    moves: Iterable[tuple[Path, Path]],
) -> list[str]:
    commands: list[str] = []
    for source, relative in moves:
        target = destination / relative
        commands.append(shlex.join(['mv', '-n', str(source), str(target)]))
    return commands


def _asset(name: str, relative: Path, encoding: str, path: Path) -> Asset:
    with path.open('rb') as source:
        digest = hashlib.file_digest(source, 'sha256').hexdigest()
    return Asset(
        name=name,
        location=RelativeFileLocation(path=relative.as_posix()),
        encoding=encoding,
        content=ContentIdentity(byte_length=path.stat().st_size, sha256=digest),
    )


def _audio_paths(root: Path) -> list[Path]:
    return [
        path
        for path in root.rglob('*')
        if path.is_file() and path.suffix.lower() in {'.wav', '.flac'}
    ]


def _flow_timestamp(path: Path, project: Path) -> tuple[str, str] | None:
    pair = _pair_from_path(path)
    if pair is None:
        return None
    dates = [
        parent.name for parent in path.parents if _DATE_DIRECTORY.fullmatch(parent.name)
    ]
    if not dates:
        return None
    return dates[0], pair[2]


def _pair_from_path(path: Path) -> tuple[str, list[int], str] | None:
    for parent in path.parents:
        if match := _PAIR.fullmatch(parent.name):
            first = int(match.group(1))
            second = int(match.group(2) or first)
            return (
                parent.name.split(' + ')[0],
                list(range(first, second + 1)),
                match.group(3),
            )
    if match := _PAIR.fullmatch(path.stem):
        first = int(match.group(1))
        second = int(match.group(2) or first)
        return path.stem.split(' + ')[0], list(range(first, second + 1)), match.group(3)
    return None


def _flow_source_name(path: Path) -> str:
    if path.stem in {'FLOW 8 (Recording)', 'MacBook Pro Microphone'}:
        return path.stem
    for parent in path.parents:
        if parent.name in {'FLOW 8 (Recording)', 'MacBook Pro Microphone'}:
            return parent.name
    return 'FLOW 8'


def _deduplicate_flow_entries(entries: list[AudioInput]) -> list[AudioInput]:
    selected: dict[tuple[str, str], AudioInput] = {}
    for entry in entries:
        key = entry.source_name, entry.track_name
        previous = selected.get(key)
        if previous is None:
            selected[key] = entry
            continue
        if _sha256(previous.path) != _sha256(entry.path):
            raise RecsError(
                f'Non-identical duplicate take files: {previous.path} and {entry.path}'
            )
    return list(selected.values())


def _audio_input(
    path: Path,
    project_name: str,
    timestamp: float,
    source_name: str,
    track_name: str,
    source_channels: list[int],
) -> AudioInput:
    return AudioInput(
        path=path,
        project_name=project_name,
        timestamp=timestamp,
        source_name=source_name,
        track_name=track_name,
        source_channels=source_channels,
    )


def _media_name(item: AudioInput) -> str:
    timestamp = datetime.fromtimestamp(item.timestamp).strftime('%Y%m%d-%H%M%S')
    return f'{item.source_name} + {item.track_name} + {timestamp}{item.path.suffix}'


def _wav_icrd_timestamp(path: Path) -> float | None:
    if path.suffix.lower() != '.wav':
        return None
    with path.open('rb') as source:
        header = source.read(12)
        if len(header) != 12 or header[:4] != b'RIFF' or header[8:] != b'WAVE':
            return None
        while header := source.read(8):
            if len(header) != 8:
                return None
            chunk_id, size = struct.unpack('<4sI', header)
            if chunk_id != b'LIST':
                source.seek(size + size % 2, 1)
                continue
            content = source.read(size)
            source.seek(size % 2, 1)
            if content[:4] != b'INFO':
                continue
            offset = 4
            while offset + 8 <= len(content):
                tag, value_size = struct.unpack('<4sI', content[offset : offset + 8])
                offset += 8
                if offset + value_size > len(content):
                    return None
                value = content[offset : offset + value_size]
                offset += value_size + value_size % 2
                if tag != b'ICRD':
                    continue
                try:
                    text = value.rstrip(b'\0').decode('utf-8')
                    value = datetime.fromisoformat(text)
                except (UnicodeDecodeError, ValueError):
                    return None
                if 'T' not in text:
                    return None
                return value.timestamp()
    return None


def _timestamp(date: str, time: str) -> float:
    return mktime(datetime.strptime(f'{date} {time}', '%Y-%m-%d %H%M%S').timetuple())


def _timestamp_from_name(name: str) -> float:
    return mktime(datetime.strptime(name, '%Y-%m-%d %H-%M-%S').timetuple())


def _timestamp_from_livetrak(name: str) -> float:
    match = _LIVETRAK_DIRECTORY.fullmatch(name)
    if match is None:
        raise RecsError(f'Invalid LiveTrak directory name: {name}')
    return mktime(
        datetime.strptime('20' + ''.join(match.groups()), '%Y%m%d%H%M%S').timetuple()
    )


def _livetrak_channels(name: str) -> list[int]:
    if name == 'MASTER':
        return []
    match = re.fullmatch(r'TRACK(\d{2})(?:_(\d{2}))?', name)
    if match is None:
        raise RecsError(f'Invalid LiveTrak track name: {name}')
    first = int(match.group(1))
    second = int(match.group(2) or first)
    return list(range(first, second + 1))


def _sha256(path: Path) -> str:
    with path.open('rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest()
