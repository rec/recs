"""Shared constraints for the declarative recsam format, not playback state."""

from collections.abc import Hashable, Iterable
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field


class Model(BaseModel, frozen=True):
    """Reject unknown fields and nonfinite numbers throughout an instrument."""

    model_config = ConfigDict(
        extra='forbid', allow_inf_nan=False, validate_default=True
    )


def unique(values: Iterable[Hashable], label: str) -> None:
    seen: set[Hashable] = set()
    for value in values:
        if value in seen:
            raise ValueError(f'Duplicate {label}: {value}')
        seen.add(value)


Identifier = Annotated[str, Field(pattern=r'^[A-Za-z0-9_-]+$')]
Text = Annotated[str, Field(min_length=1)]
MidiValue = Annotated[int, Field(strict=True, ge=0, le=127)]
Velocity = Annotated[int, Field(strict=True, ge=1, le=127)]
Frame = Annotated[int, Field(strict=True, ge=0)]
Number = Annotated[float, Field(strict=True)]
Seconds = Annotated[float, Field(strict=True, ge=0)]
Positive = Annotated[float, Field(strict=True, gt=0)]
UnitInterval = Annotated[float, Field(strict=True, ge=0, le=1)]
