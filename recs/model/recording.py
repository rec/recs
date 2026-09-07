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


class AudioStream(Model):
    kind: Literal['audio'] = 'audio'
    id: Identifier
    source_id: str = Field(min_length=1)
    stream: AudioType
    end: int = Field(ge=0, strict=True)
    fragments: list[AudioFragment] = Field(default_factory=list)
    gaps: list[Gap] = Field(default_factory=list)

    @model_validator(mode='after')
    def timeline(self) -> Self:
        fragments = sorted(self.fragments, key=lambda f: (f.start, f.count))
        for fragment in fragments:
            if fragment.start + fragment.count > self.end:
                raise ValueError('audio fragment exceeds stream extent')
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
            ):
                raise ValueError('gap overlaps captured audio')
            previous = gap.end
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
    fragments: list[EventFragment] = Field(default_factory=list)

    @model_validator(mode='after')
    def payload_schema(self) -> Self:
        timing = {'midi': 'smf', 'osc': 'osc_jsonl', 'recs_events': 'recs_events'}
        if any(f.timing != timing[self.event_schema] for f in self.fragments):
            raise ValueError('event fragment timing disagrees with its stream schema')
        return self


class Recording(Model):
    state: Literal['sealed', 'open']
    started_at: str
    ended_at: str | None = None
    observed_duration_seconds: float | None = Field(default=None, ge=0)
    journal: Identifier
    streams: list[Annotated[AudioStream | EventStream, Field(discriminator='kind')]]
    clock_observations: list[ClockObservation] = Field(default_factory=list)

    @model_validator(mode='after')
    def session_state(self) -> Self:
        if (self.state == 'sealed') != (self.ended_at is not None):
            raise ValueError('only a sealed recording has an end timestamp')
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
            if any(f.asset not in assets for f in stream.fragments):
                raise ValueError(f'stream {stream.id} references an unknown asset')
        for observation in self.body.clock_observations:
            if (
                observation.source.timebase not in clocks
                or observation.session.timebase not in clocks
            ):
                raise ValueError('clock observation references an unknown timebase')
        return self
