from enum import auto
from pathlib import Path
from typing import Annotated, Literal

import tomlkit
from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    model_validator,
)
from strenum import StrEnum
from typing_extensions import Self

from recs.base.types import Format, Subtype


class Interpolation(StrEnum):
    hold = auto()
    linear = auto()
    equal_power = auto()


class NormalizeMode(StrEnum):
    none = auto()
    limit = auto()
    normalize = auto()


class CommandKind(StrEnum):
    autocalibrate = auto()
    clip = auto()
    stitch = auto()
    split = auto()
    mix = auto()


def identifier(value: str) -> str:
    if not value or not value[0].islower():
        raise ValueError('must start with a lowercase letter')
    if any(not (c.islower() or c.isdigit() or c in '-_') for c in value):
        raise ValueError('must contain only lowercase letters, numbers, - or _')
    return value


Identifier = Annotated[str, AfterValidator(identifier)]


class SourceSpec(BaseModel, frozen=True):
    id: Identifier
    record: Path | None = None
    channel: str | None = None
    file: Path | None = None
    channels: list[int] = Field(default_factory=list)
    input_format: Format | None = None

    @model_validator(mode='after')
    def validate_location(self) -> Self:
        if (self.record is None) == (self.file is None):
            raise ValueError('source requires exactly one of record or file')
        if self.record is not None:
            if self.channel is None:
                raise ValueError('record source requires channel')
            if self.channels:
                raise ValueError('channels are only allowed for file sources')
        else:
            if self.channel is not None:
                raise ValueError('channel is only allowed for record sources')
            if self.input_format is not None:
                raise ValueError('input_format is only allowed for record sources')
            if not self.channels:
                raise ValueError('file source requires channels')
            if (
                self.channels
                != list(range(self.channels[0], self.channels[0] + len(self.channels)))
                or self.channels[0] < 1
            ):
                raise ValueError(
                    'file source channels must be consecutive and positive'
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
    target: str
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
    path: Path
    format: Format
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


class EditSpec(BaseModel, frozen=True):
    schema_version: Literal[1]
    sample_rate: int = Field(gt=0)
    media_types: list[str] = Field(default_factory=lambda: ['audio'])
    sources: list[SourceSpec] = Field(default_factory=list)
    tracks: list[TrackSpec] = Field(default_factory=list)
    buses: list[BusSpec] = Field(default_factory=list)
    clips: list[ClipSpec] = Field(default_factory=list)
    routes: list[RouteSpec] = Field(default_factory=list)
    automation: list[AutomationSpec] = Field(default_factory=list)
    outputs: list[OutputSpec] = Field(default_factory=list)

    model_config = ConfigDict(extra='forbid')


class PartialSourceSpec(BaseModel, frozen=True):
    id: Identifier | None = None
    record: Path | None = None
    channel: str | None = None
    file: Path | None = None
    channels: list[int] | None = None
    input_format: Format | None = None

    model_config = ConfigDict(extra='forbid')


class PartialTrackSpec(BaseModel, frozen=True):
    id: Identifier | None = None
    channels: int | None = Field(default=None, gt=0)

    model_config = ConfigDict(extra='forbid')


class PartialBusSpec(BaseModel, frozen=True):
    id: Identifier | None = None
    channels: int | None = Field(default=None, gt=0)
    gain: float | None = None

    model_config = ConfigDict(extra='forbid')


class PartialClipSpec(BaseModel, frozen=True):
    id: Identifier | None = None
    source: Identifier | None = None
    track: Identifier | None = None
    source_start: int | None = Field(default=None, ge=0)
    source_end: int | None = Field(default=None, gt=0)
    timeline_start: int | None = Field(default=None, ge=0)
    gain: float | None = None

    model_config = ConfigDict(extra='forbid')


class PartialRouteSpec(BaseModel, frozen=True):
    source: Identifier | None = None
    destination: Identifier | None = None
    gain: float | None = None

    model_config = ConfigDict(extra='forbid')


class PartialAutomationPoint(BaseModel, frozen=True):
    frame: int | None = Field(default=None, ge=0)
    value: float | None = None

    model_config = ConfigDict(extra='forbid')


class PartialAutomationSpec(BaseModel, frozen=True):
    target: str | None = None
    interpolation: Interpolation | None = None
    points: list[PartialAutomationPoint] | None = None

    model_config = ConfigDict(extra='forbid')


class PartialOutputSpec(BaseModel, frozen=True):
    id: Identifier | None = None
    source: Identifier | None = None
    path: Path | None = None
    format: Format | None = None
    subtype: Subtype | None = None
    start: int | None = Field(default=None, ge=0)
    end: int | None = Field(default=None, gt=0)
    normalize: NormalizeMode | None = None
    gain: float | None = None

    model_config = ConfigDict(extra='forbid')


class CommandMetadata(BaseModel, frozen=True):
    help: str = ''
    operation: CommandKind | None = None

    model_config = ConfigDict(extra='forbid')


class PartialEditSpec(BaseModel, frozen=True):
    schema_version: Literal[1] | None = None
    sample_rate: int | None = Field(default=None, gt=0)
    media_types: list[str] | None = None
    sources: list[PartialSourceSpec] | None = None
    tracks: list[PartialTrackSpec] | None = None
    buses: list[PartialBusSpec] | None = None
    clips: list[PartialClipSpec] | None = None
    routes: list[PartialRouteSpec] | None = None
    automation: list[PartialAutomationSpec] | None = None
    outputs: list[PartialOutputSpec] | None = None
    extends: str | None = None

    command: CommandMetadata | None = Field(
        default=None, validation_alias='_command', serialization_alias='_command'
    )

    model_config = ConfigDict(extra='forbid')


def parse_edit(text: str) -> EditSpec:
    return EditSpec.model_validate(tomlkit.parse(text))


def parse_partial_edit(text: str) -> PartialEditSpec:
    return PartialEditSpec.model_validate(tomlkit.parse(text))


def canonical_toml(value: EditSpec) -> str:
    data = value.model_dump(mode='json', exclude_none=True)
    return tomlkit.dumps(data)
