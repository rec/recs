from enum import StrEnum, auto
from pathlib import Path
from typing import Literal

import tomlkit
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
)
from ufor.arrangement import ArrangementScore, Interpolation
from ufor.base import Identifier
from ufor.codec import parse_score
from ufor.encoding import Format, Subtype
from ufor.interface import NormalizeMode
from ufor.references import ParameterTarget, RecordSelector


class CommandKind(StrEnum):
    autocalibrate = auto()
    clip = auto()
    stitch = auto()
    split = auto()
    mix = auto()


class PartialSourceSpec(BaseModel, frozen=True):
    name: Identifier | None = None
    record: Path | None = None
    selector: RecordSelector | None = None
    file: Path | None = None
    memory: str | None = None
    channels: list[int] | None = None
    input_format: Format | None = None

    model_config = ConfigDict(extra='forbid')


class PartialTrackSpec(BaseModel, frozen=True):
    name: Identifier | None = None
    channels: int | None = Field(default=None, gt=0)

    model_config = ConfigDict(extra='forbid')


class PartialBusSpec(BaseModel, frozen=True):
    name: Identifier | None = None
    channels: int | None = Field(default=None, gt=0)
    gain: float | None = None

    model_config = ConfigDict(extra='forbid')


class PartialClipSpec(BaseModel, frozen=True):
    name: Identifier | None = None
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
    target: ParameterTarget | None = None
    interpolation: Interpolation | None = None
    points: list[PartialAutomationPoint] | None = None

    model_config = ConfigDict(extra='forbid')


class PartialOutputSpec(BaseModel, frozen=True):
    name: Identifier | None = None
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


def parse_edit(text: str) -> ArrangementScore:
    value = parse_score(text)
    if not isinstance(value, ArrangementScore):
        raise ValueError('edit input must be an arrangement document')
    return value


def parse_partial_edit(text: str) -> PartialEditSpec:
    return PartialEditSpec.model_validate(tomlkit.parse(text))
