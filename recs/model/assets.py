"""Asset identity and portable paths, without loading payloads."""

from pathlib import PurePosixPath, PureWindowsPath
from typing import Self
from urllib.parse import urlsplit

from pydantic import Field, field_validator, model_validator

from .base import Identifier, Model


class Asset(Model):
    id: Identifier
    path: str = Field(min_length=1)
    encoding: str = Field(min_length=1)
    byte_length: int = Field(ge=0, strict=True)
    sha256: str = Field(pattern=r'^[0-9a-f]{64}$')

    @field_validator('path')
    @classmethod
    def portable_path(cls, value: str) -> str:
        path = PurePosixPath(value)
        if (
            path.is_absolute()
            or PureWindowsPath(value).drive
            or urlsplit(value).scheme
            or '\\' in value
            or '..' in path.parts
            or str(path) == '.'
        ):
            raise ValueError('asset path must remain inside the document directory')
        return value


class AudioDescription(Model):
    timebase: Identifier
    channels: list[str] = Field(min_length=1)
    frames: int = Field(ge=0, strict=True)

    @model_validator(mode='after')
    def named_channels(self) -> Self:
        if any(not c for c in self.channels):
            raise ValueError('channels must have names')
        if len(self.channels) != len(set(self.channels)):
            raise ValueError('channel names must be unique')
        return self
