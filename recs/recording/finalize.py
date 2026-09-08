"""Build common recording documents from capture evidence."""

import hashlib
import json
from pathlib import Path
from typing import Annotated

import soundfile
import tyro
from pydantic import BaseModel
from ufor.assets import Asset
from ufor.codec import document_toml
from ufor.recording import (
    AudioFragment,
    AudioStream,
    EventFragment,
    EventStream,
    Gap,
    GapReason,
    Recording,
    RecordingDocument,
    UnfinishedFile,
)
from ufor.streams import AudioType
from ufor.time import Rate, Timebase

from ..base.errors import RecsError
from ..ui import session_record
from .files import sealed_asset, verify_events


class FinalizeSession(BaseModel, frozen=True):
    session: Annotated[Path, tyro.conf.Positional]


def main(argv: list[str] | None = None) -> int:
    config = tyro.cli(FinalizeSession, args=argv, prog='recs session finalize')
    print(finalize_recording(config.session / 'session-record.jsonl'))
    return 0


def prepare_recording(journal: Path) -> tuple[RecordingDocument, list[str]]:
    root = journal.resolve().parent
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
        raise RecsError('Recording finalization requires a version 4 session header')
    header = entries[0]
    footer = (
        entries[-1]
        if isinstance(entries[-1], session_record.SessionFooter) and not errors
        else None
    )
    starts = [
        e
        for e in entries
        if isinstance(
            e, session_record.AudioFileRecord | session_record.EventFileRecord
        )
        and e.type == 'file_started'
    ]
    finishes = [
        e
        for e in entries
        if isinstance(
            e, session_record.AudioFileRecord | session_record.EventFileRecord
        )
        and e.type == 'file_finished'
    ]
    keys = [(f.stream_id, f.path) for f in finishes]
    if len(keys) != len(set(keys)):
        raise RecsError('Duplicate finished file identity in session record')
    discarded = {
        (e.stream_id, e.path)
        for e in entries
        if isinstance(e, session_record.AudioFileRecord) and e.type == 'file_discarded'
    }
    unfinished = [
        f
        for f in starts
        if (f.stream_id, f.path) not in keys and (f.stream_id, f.path) not in discarded
    ]
    if unfinished:
        notes.append(
            f'{len(unfinished)} unfinished files are listed explicitly; '
            'no payload is claimed for them and the candidate remains open.'
        )
        footer = None
    original = sealed_asset(journal, root, 'original-journal', 'recs-session-v4')
    assets: list[Asset] = [original]
    streams: list[AudioStream | EventStream] = []
    clocks: list[Timebase] = []
    observations = [
        e.observation for e in entries if isinstance(e, session_record.ClockRecord)
    ]
    for entry in entries:
        if isinstance(entry, session_record.ClockRecord):
            clocks.extend(entry.timebases)
    timelines: dict[str, list[session_record.AudioTimelineRecord]] = {}
    for entry in entries:
        if isinstance(entry, session_record.AudioTimelineRecord):
            timelines.setdefault(entry.stream_id, []).append(entry)
    for source_id in dict.fromkeys(f.stream_id for f in finishes):
        identity = 'stream-' + hashlib.sha256(source_id.encode()).hexdigest()[:16]
        files = [f for f in finishes if f.stream_id == source_id]
        kinds = {f.media_type for f in files}
        if len(kinds) != 1 or not kinds <= {'audio', 'midi', 'osc', 'key'}:
            raise RecsError(f'Unsupported or inconsistent media type for {source_id}')
        audio: list[AudioFragment] = []
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
            path = (root / finished.path).resolve()
            asset_id = (
                'asset-' + hashlib.sha256(finished.path.encode()).hexdigest()[:16]
            )
            asset = sealed_asset(path, root, asset_id, finished.format)
            assets.append(asset)
            if finished.quantity_count is None:
                raise RecsError(f'Finished file has no quantity count: {finished.path}')
            if isinstance(finished, session_record.AudioFileRecord):
                assert isinstance(started, session_record.AudioFileRecord)
                if started.clock_id != finished.clock_id:
                    raise RecsError(f'Audio clock changes within {finished.path}')
                if started.frame_count is None or finished.frame_count is None:
                    raise RecsError(
                        f'Audio has no native frame interval: {finished.path}'
                    )
                if not finished.audio_spans and (
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
                if finished.audio_spans:
                    offset = 0
                    for span in finished.audio_spans:
                        if span.asset_start != offset:
                            raise RecsError(
                                f'Audio spans do not cover the payload: {asset.path}'
                            )
                        offset += span.count
                    if offset != info.frames or offset != finished.quantity_count:
                        raise RecsError(
                            f'Audio span count disagrees with payload: {asset.path}'
                        )
                    audio.extend(
                        AudioFragment(asset=asset.id, **s.model_dump())
                        for s in finished.audio_spans
                    )
                elif info.frames == finished.quantity_count:
                    audio.append(
                        AudioFragment(
                            asset=asset.id, start=started.frame_count, count=info.frames
                        )
                    )
                else:
                    raise RecsError(
                        f'Audio payload count disagrees with capture: {asset.path}'
                    )
            else:
                assert isinstance(finished, session_record.EventFileRecord)
                assert isinstance(started, session_record.EventFileRecord)
                if (
                    finished.timebase != started.timebase
                    or finished.format != 'recs_events'
                ):
                    raise RecsError(
                        f'Event clock or encoding disagrees: {finished.path}'
                    )
                clocks.append(finished.timebase)
                events.append(
                    EventFragment(
                        asset=asset.id,
                        event_count=finished.quantity_count,
                        timing='recs_events',
                        start=finished.start_tick,
                        end=finished.end_tick,
                        observed_opened_at=started.timestamp,
                        timing_source=finished.timing_source,
                    )
                )
        if isinstance(files[0], session_record.EventFileRecord):
            if any(
                not isinstance(f, session_record.EventFileRecord)
                or f.timebase != files[0].timebase
                for f in files
            ):
                raise RecsError(f'Event clock changes within {source_id}')
            streams.append(
                EventStream(
                    id=identity,
                    source_id=source_id,
                    event_schema='recs_events',
                    event_kind=files[0].media_type,
                    timebase=files[0].timebase.id,
                    fragments=events,
                )
            )
            continue
        assert isinstance(files[0], session_record.AudioFileRecord)
        if any(
            not isinstance(f, session_record.AudioFileRecord)
            or f.clock_id != files[0].clock_id
            for f in files
        ):
            raise RecsError(f'Audio clock changes within {source_id}')
        if any(d != descriptions[0] for d in descriptions):
            raise RecsError(f'Audio layout or sample rate changes within {source_id}')
        rate, channels, source_channels = descriptions[0]
        clock = Timebase(id=files[0].clock_id, rate=Rate(numerator=rate))
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
        intervals = sorted([(f.start, f.start + f.count) for f in audio])
        for start, finish in intervals:
            if start > end:
                gaps.append(Gap(start=end, end=start, reason=GapReason.unknown))
            end = max(end, finish)
        if captures := timelines.get(source_id):
            if any(t.clock_id != clock.id or t.sample_rate != rate for t in captures):
                raise RecsError(f'Audio timeline clock disagrees: {source_id}')
            end = max(end, *(t.end for t in captures))
            gaps = recorded_gaps(end, audio, captures)
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
                source_name=files[0].source,
                track_name=files[0].track_name,
                stream=AudioType(timebase=clock.id, channels=labels),
                end=end,
                fragments=audio,
                gaps=gaps,
            )
        )
    notes.append(
        'Media files are unchanged. '
        'Original stream IDs and native frame positions are retained.'
    )
    notes.append(
        'Gap causes and clock relationships are retained only where '
        'capture evidence establishes them.'
    )
    for source_id, captures in timelines.items():
        timeline = captures[-1]
        if any(s.source_id == source_id for s in streams):
            continue
        identity = 'stream-' + hashlib.sha256(source_id.encode()).hexdigest()[:16]
        clock = Timebase(
            id=timeline.clock_id,
            rate=Rate(numerator=timeline.sample_rate),
        )
        clocks.append(clock)
        streams.append(
            AudioStream(
                id=identity,
                source_id=source_id,
                source_name=timeline.source,
                track_name=timeline.track_name,
                stream=AudioType(
                    timebase=clock.id,
                    channels=[f'input-{i}' for i in timeline.source_channels],
                ),
                end=timeline.end,
                gaps=recorded_gaps(timeline.end, [], captures),
            )
        )
    unique_clocks: dict[str, Timebase] = {}
    for clock in clocks:
        if clock.id in unique_clocks and unique_clocks[clock.id] != clock:
            raise RecsError(f'Conflicting clock definition: {clock.id}')
        unique_clocks[clock.id] = clock
    document = RecordingDocument(
        id=header.session_id or original.sha256,
        name=root.name,
        assets=assets,
        timebases=list(unique_clocks.values()),
        body=Recording(
            state='sealed' if footer else 'open',
            started_at=header.started_at,
            ended_at=footer.ended_at if footer else None,
            observed_duration_seconds=footer.duration_seconds if footer else None,
            journal=original.id,
            clock_observations=observations,
            streams=streams,
            unfinished_files=[
                UnfinishedFile(
                    source_id=f.stream_id,
                    journal_path=f.path,
                    observed_opened_at=f.timestamp,
                )
                for f in unfinished
            ],
            continued_from=str(Path(header.continued_from).with_name('recording.toml'))
            if header.continued_from
            else None,
            continued_at=[
                str(Path(e.continued_at).with_name('recording.toml'))
                for e in entries
                if isinstance(e, session_record.EventRecord) and e.continued_at
            ],
        ),
    )
    paths = {a.id: root / a.path for a in assets}
    for stream in streams:
        if isinstance(stream, EventStream):
            verify_events(stream, paths)
    return document, notes


def finalize_recording(journal: Path) -> Path:
    document, _ = prepare_recording(journal)
    path = journal.parent / 'recording.toml'
    with path.open('x') as target:
        target.write(document_toml(document))
    return path


def recorded_gaps(
    end: int,
    fragments: list[AudioFragment],
    timelines: list[session_record.AudioTimelineRecord],
) -> list[Gap]:
    known = [g for t in timelines for g in t.gaps]
    boundaries = sorted(
        {
            0,
            end,
            *(p for f in fragments for p in (f.start, f.start + f.count)),
            *(p for g in known for p in (g.start, g.end)),
        }
    )
    gaps: list[Gap] = []
    for start, finish in zip(boundaries, boundaries[1:]):
        if any(f.start <= start < f.start + f.count for f in fragments):
            continue
        reasons = {g.reason for g in known if g.start <= start < g.end}
        if len(reasons) > 1:
            raise RecsError('Conflicting capture gap observations')
        reason = next(iter(reasons), GapReason.unknown)
        if gaps and gaps[-1].end == start and gaps[-1].reason == reason:
            gaps[-1] = Gap(start=gaps[-1].start, end=finish, reason=reason)
        else:
            gaps.append(Gap(start=start, end=finish, reason=reason))
    return gaps
