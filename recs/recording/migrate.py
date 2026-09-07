"""Explicit v3 migration. Existing recorders and session readers remain unchanged."""

import hashlib
import json
from pathlib import Path
from typing import Annotated

import soundfile
import tyro
from pydantic import BaseModel

from ..base.errors import RecsError
from ..model.assets import Asset
from ..model.codec import document_toml, parse_document
from ..model.recording import (
    AudioFragment,
    AudioStream,
    EventFragment,
    EventStream,
    Gap,
    GapReason,
    Recording,
    RecordingDocument,
    UnfinishedFile,
    UnmappedAudioFragment,
)
from ..model.streams import AudioType
from ..model.time import Rate, TickRange, Timebase
from ..ui import session_record
from .files import Verification, sealed_asset, verify_recording


class MigrateSession(BaseModel, frozen=True):
    session: Annotated[Path, tyro.conf.Positional]
    paths_relative_to: Path | None = None


def main(argv: list[str] | None = None) -> int:
    config = tyro.cli(MigrateSession, args=argv, prog='recs session migrate')
    path, verification = migrate_session(config.session, config.paths_relative_to)
    print(path)
    print(
        f'Verified {verification.asset_count} assets, '
        f'{verification.audio_frames} audio frames, {verification.event_count} events.'
    )
    for note in verification.notes:
        print(note)
    return 0


def migrate_session(
    session: Path, paths_relative_to: Path | None = None
) -> tuple[Path, Verification]:
    root = session.resolve()
    journal = root / 'session-record.jsonl'
    output = root / 'recording.toml'
    snapshot = root / 'migration/session-record-v3.jsonl'
    report_path = root / 'migration/report.json'
    if not snapshot.parent.resolve().is_relative_to(root):
        raise RecsError('Migration directory escapes the session directory')
    for path in (output, snapshot, report_path):
        if path.exists():
            raise RecsError(f'Migration output already exists: {path}')
    document, notes = prepare_migration(journal, paths_relative_to)
    # No writes occur until every referenced finished payload has been verified.
    verification = verify_recording(document, root)
    original = journal.read_bytes()
    journal_asset = next(a for a in document.assets if a.id == document.body.journal)
    if hashlib.sha256(original).hexdigest() != journal_asset.sha256:
        raise RecsError(
            'Session record changed during migration; retry after capture stops'
        )
    snapshot.parent.mkdir(exist_ok=True)
    with snapshot.open('xb') as target:
        target.write(original)
    document = document.model_copy(
        update={
            'assets': [
                a.model_copy(update={'path': snapshot.relative_to(root).as_posix()})
                if a.id == document.body.journal
                else a
                for a in document.assets
            ]
        }
    )
    with output.open('x') as target:
        target.write(document_toml(document))
    restored = parse_document(output.read_text())
    if (
        restored != document
        or journal.read_bytes() != original
        or snapshot.read_bytes() != original
    ):
        raise RecsError('Written migration differs from the verified source')
    verification = verification.model_copy(update={'notes': notes})
    with report_path.open('x') as target:
        target.write(verification.model_dump_json(indent=2) + '\n')
    return output, verification


def prepare_migration(
    journal: Path, paths_relative_to: Path | None = None
) -> tuple[RecordingDocument, list[str]]:
    root = journal.resolve().parent
    path_base = root if paths_relative_to is None else paths_relative_to.resolve()
    entries, errors = session_record.read_entries(journal)
    notes: list[str] = []
    if errors:
        # Only malformed JSON at the physical final line is recoverable. A
        # complete but invalid final record is still a schema error.
        recoverable = False
        if len(errors) == 1 and 'truncated final line' in errors[0]:
            try:
                json.loads(journal.read_text().splitlines()[-1])
            except json.JSONDecodeError:
                recoverable = True
        if not recoverable:
            raise RecsError('; '.join(errors))
        notes.append(
            'Original journal has a truncated final line; candidate remains open.'
        )
    if not entries or not isinstance(entries[0], session_record.SessionHeader):
        raise RecsError('Migration requires a version 3 session header')
    header = entries[0]
    if header.continued_from or any(
        isinstance(e, session_record.EventRecord) and e.continued_at for e in entries
    ):
        raise RecsError(
            'Continuation-chain migration requires the later session cutover'
        )
    footer = (
        entries[-1]
        if isinstance(entries[-1], session_record.SessionFooter) and not errors
        else None
    )
    starts = [
        e
        for e in entries
        if isinstance(e, session_record.FileRecord) and e.type == 'file_started'
    ]
    finishes = [
        e
        for e in entries
        if isinstance(e, session_record.FileRecord) and e.type == 'file_finished'
    ]
    keys = [(f.stream_id, f.path) for f in finishes]
    if len(keys) != len(set(keys)):
        raise RecsError('Duplicate finished file identity in session record')
    unfinished = [f for f in starts if (f.stream_id, f.path) not in keys]
    if unfinished:
        notes.append(
            f'{len(unfinished)} unfinished files are listed explicitly; '
            'no payload is claimed for them and the candidate remains open.'
        )
        footer = None
    original = sealed_asset(journal, root, 'original-journal', 'recs-session-v3')
    assets: list[Asset] = [original]
    streams: list[AudioStream | EventStream] = []
    clocks: list[Timebase] = []
    for source_id in dict.fromkeys(f.stream_id for f in finishes):
        identity = 'stream-' + hashlib.sha256(source_id.encode()).hexdigest()[:16]
        files = [f for f in finishes if f.stream_id == source_id]
        kinds = {f.media_type for f in files}
        if len(kinds) != 1 or not kinds <= {'audio', 'midi', 'osc'}:
            raise RecsError(f'Unsupported or inconsistent media type for {source_id}')
        audio: list[AudioFragment] = []
        unmapped: list[UnmappedAudioFragment] = []
        events: list[EventFragment] = []
        descriptions: list[tuple[int, int, list[int] | None]] = []
        for finished in files:
            matches = [
                f
                for f in starts
                if f.stream_id == source_id and f.path == finished.path
            ]
            if len(matches) != 1:
                raise RecsError(f'Expected exactly one file start for {finished.path}')
            started = matches[0]
            if (
                started.media_type != finished.media_type
                or started.format != finished.format
            ):
                raise RecsError(f'File lifecycle metadata disagrees: {finished.path}')
            path = (path_base / finished.path).resolve()
            asset_id = (
                'asset-' + hashlib.sha256(finished.path.encode()).hexdigest()[:16]
            )
            asset = sealed_asset(path, root, asset_id, finished.format)
            assets.append(asset)
            if finished.quantity_count is None:
                raise RecsError(f'Finished file has no quantity count: {finished.path}')
            if finished.media_type == 'audio':
                if started.frame_count is None or finished.frame_count is None:
                    raise RecsError(
                        f'Audio has no native frame interval: {finished.path}'
                    )
                if (
                    finished.frame_count - started.frame_count
                    != finished.quantity_count
                ):
                    raise RecsError(
                        f'Audio frame interval disagrees with count: {finished.path}'
                    )
                info = soundfile.info(path)
                for entry in (started, finished):
                    if entry.channels is not None and entry.channels != info.channels:
                        raise RecsError(
                            'Audio channel count disagrees with journal: '
                            f'{finished.path}'
                        )
                    if (
                        entry.sample_rate is not None
                        and entry.sample_rate != info.samplerate
                    ):
                        raise RecsError(
                            f'Audio sample rate disagrees with journal: {finished.path}'
                        )
                descriptions.append(
                    (
                        info.samplerate,
                        info.channels,
                        finished.source_channels or started.source_channels,
                    )
                )
                if info.frames == finished.quantity_count:
                    audio.append(
                        AudioFragment(
                            asset=asset.id, start=started.frame_count, count=info.frames
                        )
                    )
                else:
                    unmapped.append(
                        UnmappedAudioFragment(
                            asset=asset.id,
                            count=info.frames,
                            journal_range=TickRange(
                                start=started.frame_count, end=finished.frame_count
                            ),
                        )
                    )
                    notes.append(
                        f'{asset.path}: journal span {finished.quantity_count} frames, '
                        f'payload {info.frames} frames; '
                        'timeline placement is unresolved.'
                    )
            else:
                events.append(
                    EventFragment(
                        asset=asset.id,
                        event_count=finished.quantity_count,
                        timing='smf' if finished.media_type == 'midi' else 'osc_jsonl',
                        observed_opened_at=started.timestamp,
                        timing_source=finished.timing_source or started.timing_source,
                    )
                )
        if files[0].media_type != 'audio':
            streams.append(
                EventStream(
                    id=identity,
                    source_id=source_id,
                    event_schema='midi' if files[0].media_type == 'midi' else 'osc',
                    fragments=events,
                )
            )
            continue
        if any(d != descriptions[0] for d in descriptions):
            raise RecsError(f'Audio layout or sample rate changes within {source_id}')
        rate, channels, source_channels = descriptions[0]
        clock = Timebase(
            id='clock-' + identity.removeprefix('stream-'), rate=Rate(numerator=rate)
        )
        clocks.append(clock)
        audio.sort(key=lambda f: (f.start, f.count))
        ranges = [(f.start, f.count) for f in audio]
        audio = [
            f.model_copy(update={'variant_group': f'range-{f.start}-{f.count}'})
            if ranges.count((f.start, f.count)) > 1
            else f
            for f in audio
        ]
        gaps: list[Gap] = []
        end = 0
        intervals = sorted(
            [(f.start, f.start + f.count) for f in audio]
            + [(f.journal_range.start, f.journal_range.end) for f in unmapped]
        )
        for start, finish in intervals:
            if start > end:
                gaps.append(Gap(start=end, end=start, reason=GapReason.unknown))
            end = max(end, finish)
        labels = (
            [f'input-{i}' for i in source_channels]
            if source_channels
            else [f'channel-{i}' for i in range(channels)]
        )
        if len(labels) != channels:
            raise RecsError(
                f'Source channel labels disagree with audio width: {source_id}'
            )
        streams.append(
            AudioStream(
                id=identity,
                source_id=source_id,
                stream=AudioType(timebase=clock.id, channels=labels),
                end=end,
                fragments=audio,
                unmapped_fragments=unmapped,
                gaps=gaps,
            )
        )
    notes.append(
        'Media files are unchanged. '
        'Original stream IDs and native frame positions are retained.'
    )
    notes.append(
        'Uncaptured intervals have unknown cause; '
        'no cross-stream clock alignment or trailing audio extent was inferred.'
    )
    if path_base != root:
        notes.append(
            f'Journal paths were resolved relative to {path_base}; '
            'candidate asset paths are relative to the session.'
        )
    return RecordingDocument(
        id=header.session_id or original.sha256,
        name=root.name,
        assets=assets,
        timebases=clocks,
        body=Recording(
            state='sealed' if footer else 'open',
            started_at=header.started_at,
            ended_at=footer.ended_at if footer else None,
            observed_duration_seconds=footer.duration_seconds if footer else None,
            journal=original.id,
            streams=streams,
            unfinished_files=[
                UnfinishedFile(
                    source_id=f.stream_id,
                    journal_path=f.path,
                    observed_opened_at=f.timestamp,
                )
                for f in unfinished
            ],
        ),
    ), notes
