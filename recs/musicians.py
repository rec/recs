"""Musician identities and their recording-source assignments."""

from pydantic import BaseModel, ConfigDict, Field, field_validator
from ufor.base import Identifier

from recs.entities import Entity


class Musician(Entity):
    pass


class SourceMusician(BaseModel):
    musician: Identifier
    channels: list[int] = Field(min_length=1)
    track_name: str | bool = True

    @field_validator('channels')
    @classmethod
    def valid_channels(cls, channels: list[int]) -> list[int]:
        if any(channel <= 0 for channel in channels):
            raise ValueError('Musician channels must be positive')
        if channels != sorted(set(channels)):
            raise ValueError('Musician channels must be unique and ascending')
        return channels

    model_config = ConfigDict(frozen=True)
