from pathlib import Path
from typing import Annotated, Literal, Self

import tyro
from pydantic import BaseModel, ConfigDict, Field, model_validator
from reccy.configuration import units
from reccy.configuration.tyro import unit_spec
from ufor.encoding import Format, Subtype

from recs.edit.materialized import MaterializedAudio
from recs.edit.record import ResolvedSource

TIME_SPEC = unit_spec(units.Seconds, 'TIME')


class AutocalibrateOptions(BaseModel, frozen=True):
    """Infer noise from each track's first sustained silence and keep it fixed."""

    channel: Annotated[
        list[str], tyro.conf.arg(help='SOURCE:TRACK selector; repeat to select several')
    ] = Field(default_factory=list)

    window_time: Annotated[units.Seconds, TIME_SPEC] = Field(default=0.1, gt=0)

    candidate_percentile: float = Field(default=20.0, ge=0, le=100)

    candidate_tolerance_db: float = Field(default=3.0, ge=0)

    minimum_silence_time: Annotated[units.Seconds, TIME_SPEC] = Field(default=0.5, gt=0)

    noise_percentile: float = Field(default=95.0, ge=0, le=100)

    signal_margin_db: float = Field(default=6.0, ge=0)

    analysis_floor_dbfs: float = Field(default=-160.0, lt=0)

    quiet_before: Annotated[units.Seconds, TIME_SPEC] = Field(default=1.0, ge=0)

    quiet_after: Annotated[units.Seconds, TIME_SPEC] = Field(default=2.0, ge=0)

    stop_after_quiet: Annotated[units.Seconds, TIME_SPEC] = Field(default=20.0, ge=0)

    shortest_file_time: Annotated[units.Seconds, TIME_SPEC] = Field(default=1.0, ge=0)

    longest_file_time: Annotated[units.Seconds, TIME_SPEC] = Field(default=0.0, ge=0)

    format: Format | None = None

    subtype: Subtype | None = None

    model_config = ConfigDict(extra='forbid')


class CalibrationSettings(BaseModel, frozen=True):
    window_frames: int = Field(default=4_800, gt=0)
    candidate_percentile: float = Field(default=20.0, ge=0, le=100)
    candidate_tolerance_db: float = Field(default=3.0, ge=0)
    minimum_silence_frames: int = Field(default=24_000, gt=0)
    noise_percentile: float = Field(default=95.0, ge=0, le=100)
    signal_margin_db: float = Field(default=6.0, ge=0)
    analysis_floor_dbfs: float = Field(default=-160.0, lt=0)

    model_config = ConfigDict(extra='forbid')


class SilenceSettings(BaseModel, frozen=True):
    quiet_before_frames: int = Field(default=48_000, ge=0)
    quiet_after_frames: int = Field(default=96_000, ge=0)
    stop_after_quiet_frames: int = Field(default=960_000, ge=0)
    shortest_file_frames: int = Field(default=48_000, ge=0)
    longest_file_frames: int = Field(default=0, ge=0)

    model_config = ConfigDict(extra='forbid')


class AutocalibrateOutput(BaseModel, frozen=True):
    format: Format | None = Format.flac
    subtype: Subtype | None = Subtype.pcm_24

    model_config = ConfigDict(extra='forbid')


class CalibratedThreshold(BaseModel, frozen=True):
    source: str
    silence_start: int = Field(ge=0)
    silence_end: int = Field(gt=0)
    provisional_quiet_level_dbfs: float = Field(le=0)
    measured_noise_floor: float = Field(ge=0)
    noise_floor: float = Field(ge=0)
    observed_window_count: int = Field(gt=0)
    window_count: int = Field(gt=0)

    @model_validator(mode='after')
    def validate_range(self) -> Self:
        if self.silence_end <= self.silence_start:
            raise ValueError('silence_end must be greater than silence_start')
        return self

    model_config = ConfigDict(extra='forbid')


class AutocalibrateEdit(BaseModel, frozen=True):
    schema_version: Literal[1] = 1
    kind: Literal['autocalibrate'] = 'autocalibrate'
    record: Path | None = None
    memory: str | None = None
    channels: list[str] = Field(default_factory=list)
    sample_rate: int | None = Field(default=None, gt=0)
    calibration: CalibrationSettings = CalibrationSettings()
    silence: SilenceSettings = SilenceSettings()
    output: AutocalibrateOutput = AutocalibrateOutput()
    thresholds: list[CalibratedThreshold] = Field(default_factory=list)

    @model_validator(mode='after')
    def validate_source(self) -> Self:
        if (self.record is None) == (self.memory is None):
            raise ValueError('autocalibration requires exactly one of record or memory')
        return self

    model_config = ConfigDict(extra='forbid')


class LevelWindow(BaseModel, frozen=True):
    start: int = Field(ge=0)
    end: int = Field(gt=0)
    level_dbfs: float
    coverage_start: int = Field(ge=0)
    coverage_end: int = Field(gt=0)

    @model_validator(mode='after')
    def validate_ranges(self) -> Self:
        if self.end <= self.start:
            raise ValueError('window end must be greater than start')
        if not self.coverage_start <= self.start < self.end <= self.coverage_end:
            raise ValueError('window must remain inside observed coverage')
        return self

    model_config = ConfigDict(extra='forbid')


class FrameRange(BaseModel, frozen=True):
    start: int = Field(ge=0)
    end: int = Field(gt=0)

    @model_validator(mode='after')
    def validate_range(self) -> Self:
        if self.end <= self.start:
            raise ValueError('range end must be greater than start')
        return self

    model_config = ConfigDict(extra='forbid')


class PreparedAutocalibrate(BaseModel, frozen=True):
    edit: AutocalibrateEdit
    sources: dict[str, ResolvedSource]
    audio: dict[str, MaterializedAudio]
    track_ids: dict[str, str]
    intervals: dict[str, list[FrameRange]]

    model_config = ConfigDict(extra='forbid', arbitrary_types_allowed=True)
