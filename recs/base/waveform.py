import math

from pydantic import BaseModel, Field, field_validator, model_validator


class WaveformTrackLayout(BaseModel, frozen=True):
    channels: list[int] = Field(min_length=1, max_length=2)
    name: str = ''

    @field_validator('channels')
    @classmethod
    def validate_channels(cls, channels: list[int]) -> list[int]:
        if channels[0] <= 0:
            raise ValueError('Waveform channels must be positive')
        if len(channels) == 2 and channels[1] != channels[0] + 1:
            raise ValueError('Waveform stereo channels must be consecutive')
        return channels


class WaveformLayoutData(BaseModel, frozen=True):
    source: str = Field(min_length=1)
    generation: int = Field(ge=1)
    sample_rate: int = Field(gt=0)
    bucket_frames: int = Field(gt=0)
    tracks: list[WaveformTrackLayout] = Field(min_length=1)


class WaveformTrackData(BaseModel, frozen=True):
    channels: list[int] = Field(min_length=1, max_length=2)
    minimum: list[list[float]]
    maximum: list[list[float]]

    @field_validator('channels')
    @classmethod
    def validate_channels(cls, channels: list[int]) -> list[int]:
        if channels[0] <= 0:
            raise ValueError('Waveform channels must be positive')
        if len(channels) == 2 and channels[1] != channels[0] + 1:
            raise ValueError('Waveform stereo channels must be consecutive')
        return channels

    @model_validator(mode='after')
    def validate_extrema(self) -> 'WaveformTrackData':
        if len(self.minimum) != len(self.channels):
            raise ValueError('Waveform minimum channel count does not match channels')
        if len(self.maximum) != len(self.channels):
            raise ValueError('Waveform maximum channel count does not match channels')
        lengths = {len(v) for v in [*self.minimum, *self.maximum]}
        if len(lengths) > 1:
            raise ValueError('Waveform channel envelopes have different lengths')
        for minimum, maximum in zip(self.minimum, self.maximum, strict=True):
            for low, high in zip(minimum, maximum, strict=True):
                if not math.isfinite(low) or not math.isfinite(high):
                    raise ValueError('Waveform extrema must be finite')
                if low > high:
                    raise ValueError('Waveform minimum exceeds maximum')
        return self


class WaveformBatchData(BaseModel, frozen=True):
    source: str = Field(min_length=1)
    generation: int = Field(ge=1)
    sequence: int = Field(ge=0)
    sample_rate: int = Field(gt=0)
    bucket_frames: int = Field(gt=0)
    start_frame: int = Field(ge=0)
    start_timestamp: float
    present: list[bool] = Field(min_length=1)
    tracks: list[WaveformTrackData] = Field(min_length=1)
    dropped_batches: int = Field(default=0, ge=0)

    @model_validator(mode='after')
    def validate_bucket_counts(self) -> 'WaveformBatchData':
        if not math.isfinite(self.start_timestamp):
            raise ValueError('Waveform timestamp must be finite')
        bucket_count = len(self.present)
        for track in self.tracks:
            if track.minimum and len(track.minimum[0]) != bucket_count:
                raise ValueError('Waveform track length does not match present')
        return self
