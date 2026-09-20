import json
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Annotated, Literal, Self

import tyro
from pydantic import BaseModel, Field, model_validator
from ufor.recording import AudioStream, EventStream

from ..base.errors import RecsError
from . import legacy, session_record
from .files import asset_content, asset_path
from .read import read_recording

RECORD_GLOB = 'recording.toml'


class SessionsCli(BaseModel, frozen=True):
    """Search recording documents and journals without decoding media.

    Filters combine with AND. Text matching is case-insensitive substring matching.
    Results use path order; dates use the calendar date as recorded, not file times.
    """

    root: Annotated[Path, tyro.conf.Positional] = Path()
    json_output: Annotated[bool, tyro.conf.arg(name='json')] = False
    since: date | None = None
    """Inclusive capture date (YYYY-MM-DD); unknown dates do not match."""
    before: date | None = None
    """Exclusive capture date (YYYY-MM-DD); unknown dates do not match."""
    source: str | None = None
    """Source name or identity, including event sources."""
    track: str | None = None
    """Source-qualified audio track name."""
    marker: str | None = None
    """Journal marker label or pressed key."""
    media: Literal['audio', 'midi', 'osc', 'key', 'ump', 'events'] | None = None
    incomplete: bool = False
    """Only open recordings or recordings with unresolved audio placement."""
    warning: str | None = None
    """Warning/diagnostic text; an empty string matches any warning."""
    limit: int = Field(default=100, ge=1)
    """Maximum matching sessions returned; unreadable entries still report errors."""

    @model_validator(mode='after')
    def date_range(self) -> Self:
        if (
            self.since is not None
            and self.before is not None
            and self.since >= self.before
        ):
            raise ValueError('before must be later than since')
        return self


class ShowCli(BaseModel, frozen=True):
    """Inspect one finalized recording session."""

    path: Annotated[Path, tyro.conf.Positional]
    json_output: Annotated[bool, tyro.conf.arg(name='json')] = False


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
    sources: list[str] = Field(default_factory=list)
    marker_labels: list[str] = Field(default_factory=list)
    media_kinds: list[str] = Field(default_factory=list)
    matched_filters: list[str] = Field(default_factory=list)


def main(argv: list[str]) -> int:
    cfg = tyro.cli(SessionsCli, args=argv, prog='recs sessions')
    summaries = scan(cfg)
    if cfg.json_output:
        print(json.dumps([s.model_dump(mode='json') for s in summaries], indent=2))
    else:
        _print_summaries(summaries)
    return 0


def scan(cfg: SessionsCli) -> list[SessionSummary]:
    root = cfg.root
    if root.match(RECORD_GLOB):
        directories = [root.parent]
    elif any(root.glob(RECORD_GLOB)):
        directories = [root]
    else:
        directories = sorted({p.parent for p in root.glob(f'**/{RECORD_GLOB}')})
    summaries: list[SessionSummary] = []
    truncated = False
    for path in directories:
        if (summary := summarize(path)) is None:
            continue
        if (matches := _matches(summary, cfg)) is None:
            continue
        if len(summaries) >= cfg.limit:
            truncated = True
            continue
        summaries.append(summary.model_copy(update={'matched_filters': matches}))
    if truncated:
        print(
            f'Results limited to {cfg.limit}; increase --limit for more matches.',
            file=sys.stderr,
        )
    return summaries


def summarize(path: Path) -> SessionSummary | None:
    if path.match(RECORD_GLOB):
        path = path.parent
    record_path = path / RECORD_GLOB
    if not record_path.is_file():
        return None
    try:
        document = read_recording(record_path)
    except (RecsError, ValueError) as error:
        print(f'{record_path}: {error}', file=sys.stderr)
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
            journal_path = (path / asset_path(asset)).resolve()
            if not journal_path.is_relative_to(path.resolve()):
                raise RecsError('Journal escapes the session directory')
            journal = (
                legacy.read(journal_path)
                if asset.encoding == 'recs-session-v3'
                else session_record.read(journal_path)
            )
    except (OSError, ValueError, RecsError) as error:
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
            {(path / asset_path(assets[a])).parent.as_posix() for a in media}
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
        total_bytes=sum(asset_content(assets[a]).byte_length for a in media),
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
        sources=sorted(
            {s.source_id for s in body.streams}
            | {s.source_name for s in audio if s.source_name}
        ),
        marker_labels=sorted(
            {
                e.label or e.key or ''
                for e in journal.events
                if e.type in {'mark', 'key_pressed'}
            }
        )
        if journal
        else [],
        media_kinds=sorted(
            ({'audio'} if audio else set())
            | {
                s.event_kind
                if s.event_kind in {'midi', 'osc', 'key', 'ump'}
                else s.event_schema
                if s.event_schema in {'midi', 'osc'}
                else 'events'
                for s in events
            }
        ),
    )


def show(argv: list[str]) -> int:
    cfg = tyro.cli(ShowCli, args=argv, prog='recs session show')
    if (value := summarize(cfg.path)) is None:
        print(f'{cfg.path}: not a readable recs record', file=sys.stderr)
        return 1
    if cfg.json_output:
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
        for match in value.matched_filters:
            print(f'  matched: {match}')


def _matches(summary: SessionSummary, cfg: SessionsCli) -> list[str] | None:
    matches: list[str] = []
    if cfg.since is not None or cfg.before is not None:
        try:
            captured = datetime.fromisoformat(summary.started_at).date()
        except ValueError:
            return None
        if cfg.since is not None:
            if captured < cfg.since:
                return None
            matches.append(f'capture date {captured} >= {cfg.since}')
        if cfg.before is not None:
            if captured >= cfg.before:
                return None
            matches.append(f'capture date {captured} < {cfg.before}')
    for label, needle, values in (
        ('source', cfg.source, summary.sources),
        ('track', cfg.track, summary.tracks),
        ('marker', cfg.marker, summary.marker_labels),
        ('warning', cfg.warning, summary.warnings),
    ):
        if needle is not None:
            found = [v for v in values if needle.casefold() in v.casefold()]
            if not found:
                return None
            matches.append(f'{label}: {", ".join(found)}')
    if cfg.media is not None:
        if cfg.media not in summary.media_kinds:
            return None
        matches.append(f'media: {cfg.media}')
    if cfg.incomplete:
        if summary.state == 'sealed' and not summary.unresolved_audio_files:
            return None
        matches.append(
            f'incomplete: state={summary.state}, '
            f'unresolved audio files={summary.unresolved_audio_files}'
        )
    return matches


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
