"""Recording evidence: sealed assets, native fragments, and explicit gaps."""

from enum import StrEnum, auto
from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from .assets import Asset
from .base import Identifier, Model, unique
from .document import Document
from .streams import AudioType
from .time import ClockObservation, TickRange, Timebase


class GapReason(StrEnum):
    unknown = auto()
    silence_suppressed = auto()
    input_overflow = auto()
    disconnected = auto()


class Gap(TickRange):
    reason: GapReason


class AudioFragment(Model):
    asset: Identifier
    asset_start: int = Field(default=0, ge=0, strict=True)
    start: int = Field(ge=0, strict=True)
    count: int = Field(ge=0, strict=True)
    variant_group: Identifier | None = None


class UnmappedAudioFragment(Model):
    asset: Identifier
    count: int = Field(ge=0, strict=True)
    journal_range: TickRange
    reason: Literal['frame_count_mismatch'] = 'frame_count_mismatch'


class AudioStream(Model):
    kind: Literal['audio'] = 'audio'
    id: Identifier
    source_id: str = Field(min_length=1)
    stream: AudioType
    end: int = Field(ge=0, strict=True)
    fragments: list[AudioFragment] = Field(default_factory=list)
    unmapped_fragments: list[UnmappedAudioFragment] = Field(default_factory=list)
    gaps: list[Gap] = Field(default_factory=list)

    @model_validator(mode='after')
    def timeline(self) -> Self:
        fragments = sorted(self.fragments, key=lambda f: (f.start, f.count))
        unique(
            [f'{f.asset}:{f.asset_start}:{f.start}' for f in fragments],
            'fragment identities',
        )
        for fragment in fragments:
            if fragment.start + fragment.count > self.end:
                raise ValueError('audio fragment exceeds stream extent')
        for fragment in self.unmapped_fragments:
            if (
                fragment.journal_range.start < 0
                or fragment.journal_range.end > self.end
            ):
                raise ValueError('unmapped journal interval exceeds stream extent')
        for left, right in zip(fragments, fragments[1:]):
            if left.start + left.count <= right.start:
                continue
            if not (
                left.variant_group is not None
                and left.variant_group == right.variant_group
                and (left.start, left.count) == (right.start, right.count)
                and left.asset != right.asset
            ):
                raise ValueError('overlapping audio fragments require exact variants')
        previous = 0
        for gap in self.gaps:
            if gap.start < previous or gap.end > self.end:
                raise ValueError('gaps must be ordered and within the stream extent')
            if any(
                gap.start < f.start + f.count and f.start < gap.end for f in fragments
            ) or any(
                gap.start < f.journal_range.end and f.journal_range.start < gap.end
                for f in self.unmapped_fragments
            ):
                raise ValueError('gap overlaps captured audio')
            previous = gap.end
        intervals = sorted(
            [(f.start, f.start + f.count) for f in fragments]
            + [(g.start, g.end) for g in self.gaps]
            + [
                (f.journal_range.start, f.journal_range.end)
                for f in self.unmapped_fragments
            ]
        )
        covered = 0
        for start, end in intervals:
            if start > covered:
                raise ValueError('uncaptured audio intervals must have explicit gaps')
            covered = max(covered, end)
        if covered != self.end:
            raise ValueError('uncaptured audio intervals must have explicit gaps')
        return self


class EventFragment(Model):
    asset: Identifier
    event_count: int = Field(ge=0, strict=True)
    timing: Literal['smf', 'osc_jsonl', 'recs_events']
    observed_opened_at: str | None = None
    timing_source: str | None = None


class EventStream(Model):
    kind: Literal['events'] = 'events'
    id: Identifier
    source_id: str = Field(min_length=1)
    event_schema: Literal['midi', 'osc', 'recs_events']
    timebase: Identifier | None = None
    fragments: list[EventFragment] = Field(default_factory=list)

    @model_validator(mode='after')
    def payload_schema(self) -> Self:
        if (self.event_schema == 'recs_events') != (self.timebase is not None):
            raise ValueError('only native event streams declare a document timebase')
        timing = {'midi': 'smf', 'osc': 'osc_jsonl', 'recs_events': 'recs_events'}
        if any(f.timing != timing[self.event_schema] for f in self.fragments):
            raise ValueError('event fragment timing disagrees with its stream schema')
        return self


class UnfinishedFile(Model):
    source_id: str
    journal_path: str
    observed_opened_at: str


class Recording(Model):
    state: Literal['sealed', 'open']
    started_at: str
    ended_at: str | None = None
    observed_duration_seconds: float | None = Field(default=None, ge=0)
    journal: Identifier
    streams: list[Annotated[AudioStream | EventStream, Field(discriminator='kind')]]
    clock_observations: list[ClockObservation] = Field(default_factory=list)
    unfinished_files: list[UnfinishedFile] = Field(default_factory=list)

    @model_validator(mode='after')
    def session_state(self) -> Self:
        if (self.state == 'sealed') != (self.ended_at is not None):
            raise ValueError('only a sealed recording has an end timestamp')
        if self.state == 'sealed' and self.unfinished_files:
            raise ValueError('a recording with unfinished files must remain open')
        unique([s.id for s in self.streams], 'stream IDs')
        return self


class RecordingDocument(Document):
    kind: Literal['recording'] = 'recording'
    assets: list[Asset]
    timebases: list[Timebase] = Field(default_factory=list)
    body: Recording

    @model_validator(mode='after')
    def references(self) -> Self:
        unique([a.id for a in self.assets], 'asset IDs')
        unique([t.id for t in self.timebases], 'timebase IDs')
        assets = {a.id for a in self.assets}
        clocks = {t.id for t in self.timebases}
        if self.body.journal not in assets:
            raise ValueError('recording journal references an unknown asset')
        for stream in self.body.streams:
            if isinstance(stream, AudioStream) and stream.stream.timebase not in clocks:
                raise ValueError(f'stream {stream.id} references an unknown timebase')
            if (
                isinstance(stream, EventStream)
                and stream.timebase is not None
                and stream.timebase not in clocks
            ):
                raise ValueError(f'stream {stream.id} references an unknown timebase')
            if any(f.asset not in assets for f in stream.fragments):
                raise ValueError(f'stream {stream.id} references an unknown asset')
            if isinstance(stream, AudioStream) and any(
                f.asset not in assets for f in stream.unmapped_fragments
            ):
                raise ValueError(f'stream {stream.id} references an unknown asset')
        for observation in self.body.clock_observations:
            if (
                observation.source.timebase not in clocks
                or observation.session.timebase not in clocks
            ):
                raise ValueError('clock observation references an unknown timebase')
        return self
