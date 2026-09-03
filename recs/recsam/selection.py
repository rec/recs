"""Alternate takes, choking, sustain, and articulation switches."""

from pydantic import Field, StrictBool, model_validator
from typing_extensions import Self

from . import enums
from .base import Bipolar, Identifier, Key, Model, Positive, UnitInterval, unique


class Selection(Model):
    id: Identifier
    mode: enums.SelectionMode


class Choke(Model):
    group: Identifier
    mode: enums.ChokeMode
    fade_seconds: Positive | None = None

    @model_validator(mode='after')
    def fade_time_matches_mode(self) -> Self:
        if self.mode == enums.ChokeMode.fade:
            if self.fade_seconds is None:
                raise ValueError('fade requires fade_seconds')
        elif 'fade_seconds' in self.model_fields_set:
            raise ValueError('fade_seconds is only allowed for fade')
        return self


class Sustain(Model):
    control: Identifier
    threshold: UnitInterval = Field(default=0.5, gt=0)


class KeySwitch(Model):
    key: Key
    articulation: Identifier
    behavior: enums.KeyBehavior = enums.KeyBehavior.latched
    consume: StrictBool = True


class ControlSwitch(Model):
    control: Identifier
    minimum_value: Bipolar
    maximum_value: Bipolar
    articulation: Identifier

    @model_validator(mode='after')
    def ordered_range(self) -> Self:
        if self.minimum_value > self.maximum_value:
            raise ValueError('minimum_value must not exceed maximum_value')
        return self


class Articulations(Model):
    ids: list[Identifier] = Field(min_length=1)
    default: Identifier
    keys: list[KeySwitch] = Field(default_factory=list)
    controls: list[ControlSwitch] = Field(default_factory=list)

    @model_validator(mode='after')
    def valid_switches(self) -> Self:
        unique(self.ids, 'articulation ID')
        unique((k.key for k in self.keys), 'keyswitch key')
        references = [
            self.default,
            *(k.articulation for k in self.keys),
            *(c.articulation for c in self.controls),
        ]
        if missing := set(references).difference(self.ids):
            raise ValueError(f'Unknown articulations: {sorted(missing)}')
        previous: ControlSwitch | None = None
        for switch in sorted(self.controls, key=lambda c: (c.control, c.minimum_value)):
            if (
                previous is not None
                and switch.control == previous.control
                and switch.minimum_value <= previous.maximum_value
            ):
                raise ValueError(
                    f'Overlapping articulation ranges for control {switch.control}'
                )
            previous = switch
        return self
