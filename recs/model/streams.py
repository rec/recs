"""The implemented audio port contract and file render destinations."""

from pathlib import Path
from typing import Literal, Self

from pydantic import Field, model_validator

from ..base.types import Format, Subtype
from .base import Identifier, Model, unique


class AudioType(Model):
    family: Literal['sampled'] = 'sampled'
    quantity: Literal['audio_amplitude'] = 'audio_amplitude'
    unit: Literal['full_scale'] = 'full_scale'
    timebase: Identifier
    channels: list[str] = Field(min_length=1)

    @model_validator(mode='after')
    def channel_names(self) -> Self:
        unique(self.channels, 'channel names')
        if any(not c for c in self.channels):
            raise ValueError('channel names must not be empty')
        return self


class FileDestination(Model):
    port: Identifier
    path: Path
    format: Format
    subtype: Subtype | None = None
