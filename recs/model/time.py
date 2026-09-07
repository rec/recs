"""Exact native ticks; converting positions never resamples quantity data."""

from fractions import Fraction
from typing import Literal, Self

from pydantic import Field, model_validator

from .base import Identifier, Model


class Rate(Model):
    numerator: int = Field(gt=0, strict=True)
    denominator: int = Field(default=1, gt=0, strict=True)


class Timebase(Model):
    id: Identifier
    kind: Literal['physical'] = 'physical'
    rate: Rate


class Position(Model):
    timebase: Identifier
    tick: int = Field(strict=True)


class ClockObservation(Model):
    source: Position
    session: Position
    uncertainty_ticks: int | None = Field(default=None, ge=0, strict=True)
    timing_source: str = Field(min_length=1)
    segment: int = Field(default=0, ge=0, strict=True)


class TickRange(Model):
    start: int = Field(strict=True)
    end: int = Field(strict=True)

    @model_validator(mode='after')
    def ordered(self) -> Self:
        if self.end <= self.start:
            raise ValueError('end must be greater than start')
        return self


def convert_tick(tick: int, source: Timebase, destination: Timebase) -> int:
    """Round an absolute converted position once, with ties to even."""
    return round(
        Fraction(tick * source.rate.denominator, source.rate.numerator)
        * Fraction(destination.rate.numerator, destination.rate.denominator)
    )
