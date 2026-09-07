"""Structured content references, independent of CLI selector spelling."""

from typing import Literal, Self

from pydantic import Field, model_validator

from .base import Identifier, Model


class RecordSelector(Model):
    source: str = Field(min_length=1)
    track: str = Field(min_length=1)
    channel: int | None = Field(default=None, ge=0, strict=True)


class ParameterTarget(Model):
    kind: Literal['clip', 'bus', 'route']
    node: Identifier
    parameter: Literal['gain'] = 'gain'
    destination: Identifier | None = None

    @model_validator(mode='after')
    def addressed_route(self) -> Self:
        if (self.kind == 'route') != (self.destination is not None):
            raise ValueError('only route targets require a destination')
        return self
