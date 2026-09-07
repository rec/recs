from enum import StrEnum, auto
from pathlib import Path
from typing import Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    model_validator,
)

from ..base.types import Format, Subtype
from .base import Identifier
from .document import Document
from .references import ParameterTarget, RecordSelector
from .time import Timebase


class Interpolation(StrEnum):
    hold = auto()
    linear = auto()
    equal_power = auto()


class NormalizeMode(StrEnum):
    none = auto()
    limit = auto()
    normalize = auto()


class SourceSpec(BaseModel, frozen=True):
    id: Identifier
    record: Path | None = None
    selector: RecordSelector | None = None
    file: Path | None = None
    memory: str | None = None
    channels: list[int] = Field(default_factory=list)
    input_format: Format | None = None

    @model_validator(mode='after')
    def validate_location(self) -> Self:
        locations = [
            self.record is not None,
            self.file is not None,
            self.memory is not None,
        ]
        if sum(locations) != 1:
            raise ValueError('source requires exactly one of record, file, or memory')
        if self.record is not None:
            if self.selector is None:
                raise ValueError('record source requires selector')
            if self.channels:
                raise ValueError(
                    'channels are only allowed for file and memory sources'
                )
        else:
            if self.selector is not None:
                raise ValueError('selector is only allowed for record sources')
            if self.input_format is not None:
                raise ValueError('input_format is only allowed for record sources')
            if not self.channels:
                raise ValueError('file and memory sources require channels')
            if (
                self.channels
                != list(range(self.channels[0], self.channels[0] + len(self.channels)))
                or self.channels[0] < 0
            ):
                raise ValueError(
                    'file source channels must be consecutive and nonnegative'
                )
        return self

    model_config = ConfigDict(extra='forbid')


class TrackSpec(BaseModel, frozen=True):
    id: Identifier
    channels: int = Field(gt=0)

    model_config = ConfigDict(extra='forbid')


class BusSpec(BaseModel, frozen=True):
    id: Identifier
    channels: int = Field(gt=0)
    gain: float = 1.0

    model_config = ConfigDict(extra='forbid')


class ClipSpec(BaseModel, frozen=True):
    id: Identifier
    source: Identifier
    track: Identifier
    source_start: int = Field(ge=0)
    source_end: int = Field(gt=0)
    timeline_start: int = Field(ge=0)
    gain: float = 1.0

    @model_validator(mode='after')
    def validate_interval(self) -> Self:
        if self.source_end <= self.source_start:
            raise ValueError('source_end must be greater than source_start')
        return self

    model_config = ConfigDict(extra='forbid')


class RouteSpec(BaseModel, frozen=True):
    source: Identifier
    destination: Identifier
    gain: float = 1.0

    model_config = ConfigDict(extra='forbid')


class AutomationPoint(BaseModel, frozen=True):
    frame: int = Field(ge=0)
    value: float

    model_config = ConfigDict(extra='forbid')


class AutomationSpec(BaseModel, frozen=True):
    target: ParameterTarget
    interpolation: Interpolation = Interpolation.linear
    points: list[AutomationPoint] = Field(min_length=1)

    @model_validator(mode='after')
    def validate_points(self) -> Self:
        frames = [p.frame for p in self.points]
        if any(a >= b for a, b in zip(frames, frames[1:], strict=False)):
            raise ValueError('automation point frames must be strictly increasing')
        if self.interpolation == Interpolation.equal_power and any(
            p.value < 0 for p in self.points
        ):
            raise ValueError('equal-power automation values cannot be negative')
        return self

    model_config = ConfigDict(extra='forbid')


class OutputSpec(BaseModel, frozen=True):
    id: Identifier
    source: Identifier
    path: Path | None = None
    format: Format | None = None
    subtype: Subtype | None = None
    start: int | None = Field(default=None, ge=0)
    end: int | None = Field(default=None, gt=0)
    normalize: NormalizeMode = NormalizeMode.none
    gain: float = 1.0

    @model_validator(mode='after')
    def validate_interval(self) -> Self:
        if self.start is not None and self.end is not None and self.end <= self.start:
            raise ValueError('output end must be greater than start')
        return self

    model_config = ConfigDict(extra='forbid')


class Arrangement(BaseModel, frozen=True):
    timebase: Identifier
    media_types: list[str] = Field(default_factory=lambda: ['audio'])
    sources: list[SourceSpec] = Field(default_factory=list)
    tracks: list[TrackSpec] = Field(default_factory=list)
    buses: list[BusSpec] = Field(default_factory=list)
    clips: list[ClipSpec] = Field(default_factory=list)
    routes: list[RouteSpec] = Field(default_factory=list)
    automation: list[AutomationSpec] = Field(default_factory=list)
    outputs: list[OutputSpec] = Field(default_factory=list)

    model_config = ConfigDict(extra='forbid')


class ArrangementDocument(Document):
    kind: Literal['arrangement'] = 'arrangement'
    timebases: list[Timebase] = Field(min_length=1, max_length=1)
    body: Arrangement

    @model_validator(mode='after')
    def audio_clock(self) -> Self:
        clock = self.timebases[0]
        if self.body.timebase != clock.id:
            raise ValueError('arrangement references an unknown timebase')
        if clock.rate.denominator != 1:
            raise ValueError(
                'audio arrangement rate must be integer samples per second'
            )
        return self
