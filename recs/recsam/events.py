"""Frame-timed performance events; hosts adapt MIDI, OSC, or direct callers."""

from typing import Annotated, Literal

from pydantic import Field, model_validator
from typing_extensions import Self

from . import base, enums


class Trigger(base.Model):
    kind: Literal['trigger'] = 'trigger'
    frame: base.Frame
    part: base.Identifier
    trigger_id: base.Identifier
    key: base.Key
    velocity: base.UnitInterval = 1.0
    pitch_hz: base.Positive | None = None
    controls: dict[base.Identifier, base.Bipolar] = Field(default_factory=dict)


class Release(base.Model):
    kind: Literal['release'] = 'release'
    frame: base.Frame
    part: base.Identifier
    trigger_id: base.Identifier


class ControlChange(base.Model):
    kind: Literal['control_change'] = 'control_change'
    frame: base.Frame
    control: base.Identifier
    value: base.Bipolar
    scope: Literal[enums.Scope.instrument, enums.Scope.part, enums.Scope.trigger]

    part: base.Identifier | None = None
    trigger_id: base.Identifier | None = None

    @model_validator(mode='after')
    def addressed_scope(self) -> Self:
        if self.scope == enums.Scope.instrument:
            if self.part is not None or self.trigger_id is not None:
                raise ValueError('Instrument controls have no part or trigger_id')
        elif self.part is None:
            raise ValueError('Part and trigger controls require part')
        if self.scope == enums.Scope.trigger:
            if self.trigger_id is None:
                raise ValueError('Trigger controls require trigger_id')
        elif self.trigger_id is not None:
            raise ValueError('trigger_id is only allowed for trigger controls')
        return self


PerformanceEvent = Annotated[
    Trigger | Release | ControlChange, Field(discriminator='kind')
]
