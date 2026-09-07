"""A native event sequence has an explicit extent independent of event count."""

from typing import Literal, Self

from pydantic import Field, model_validator

from .base import Identifier, Model, unique
from .document import Document
from .events import StoredEvent
from .time import Timebase


class Sequence(Model):
    timebase: Identifier
    start: int = Field(default=0, strict=True)
    end: int = Field(strict=True)
    events: list[StoredEvent] = Field(default_factory=list)

    @model_validator(mode='after')
    def event_order(self) -> Self:
        if self.end < self.start:
            raise ValueError('sequence end precedes its start')
        unique([str(e.ordinal) for e in self.events], 'event ordinals')
        order = [(e.tick, e.ordinal) for e in self.events]
        if order != sorted(order):
            raise ValueError('events must be in timestamp and ordinal order')
        if any(not self.start <= e.tick < self.end for e in self.events):
            raise ValueError('event is outside the sequence extent')
        return self


class SequenceDocument(Document):
    kind: Literal['sequence'] = 'sequence'
    timebases: list[Timebase] = Field(min_length=1)
    body: Sequence

    @model_validator(mode='after')
    def clock_reference(self) -> Self:
        unique([t.id for t in self.timebases], 'timebase IDs')
        if self.body.timebase not in {t.id for t in self.timebases}:
            raise ValueError('sequence references an unknown timebase')
        return self
