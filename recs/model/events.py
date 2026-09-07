"""Native-timed stored events. Transport and performance state live in hosts."""

import base64
import binascii
from typing import Annotated, Literal

from pydantic import Field, field_validator

from .base import Model


class Event(Model):
    tick: int = Field(strict=True)
    ordinal: int = Field(ge=0, strict=True)


class MidiEvent(Event):
    kind: Literal['midi'] = 'midi'
    data: list[Annotated[int, Field(strict=True)]] = Field(min_length=1)

    @field_validator('data')
    @classmethod
    def bytes_only(cls, value: list[int]) -> list[int]:
        if any(not 0 <= v <= 255 for v in value):
            raise ValueError('MIDI data must contain bytes')
        return value


class OscMessage(Model):
    path: str
    types: str
    args: list[str | int | float | bool | None]


class OscDecodeError(Model):
    error: str


class Endpoint(Model):
    host: str
    port: int = Field(ge=0, le=65535)


class OscEvent(Event):
    kind: Literal['osc'] = 'osc'
    data_b64: str
    direction: Literal['in', 'out']
    source_time: str | None = None
    endpoint: Endpoint | None = None
    decoded: list[OscMessage | OscDecodeError] = Field(default_factory=list)
    reason: str | None = None

    @field_validator('data_b64')
    @classmethod
    def packet_bytes(cls, value: str) -> str:
        try:
            base64.b64decode(value, validate=True)
        except binascii.Error as error:
            raise ValueError('OSC packet must be valid base64') from error
        return value


class KeyEvent(Event):
    kind: Literal['key'] = 'key'
    key: str = Field(min_length=1)
    action: Literal['press', 'release']
    text: str | None = None
    modifiers: list[str] = Field(default_factory=list)
    repeat: bool = False


StoredEvent = Annotated[MidiEvent | OscEvent | KeyEvent, Field(discriminator='kind')]
