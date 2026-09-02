"""Typed curves: each input exposes only the fields meaningful for that input."""

from typing import Annotated, Literal

from pydantic import Field, StrictInt, model_validator
from typing_extensions import Self

from . import enums
from .base import Identifier, MidiValue, Model, Number, Seconds


class Point(Model):
    input: StrictInt | Number
    amount: Number


class Modulation(Model):
    target: str
    input: enums.Input
    operation: enums.Operation
    points: list[Point] = Field(min_length=1)
    interpolation: enums.Interpolation = enums.Interpolation.linear

    @model_validator(mode='after')
    def valid_curve(self) -> Self:
        if self.operation != target_operation(self.target):
            raise ValueError(f'{self.target} requires {target_operation(self.target)}')
        if self.target.startswith(('envelope.', 'envelopes.')) and self.input not in (
            enums.Input.note,
            enums.Input.velocity,
        ):
            raise ValueError('Envelope duration targets require note or velocity input')
        previous: float | None = None
        for point in self.points:
            validate_input_value(self.input, point.input)
            if previous is not None and point.input <= previous:
                raise ValueError('Point inputs must be strictly increasing')
            if self.operation == enums.Operation.multiply and point.amount <= 0:
                raise ValueError('Multiplicative amounts must be positive')
            previous = point.input
        return self


class NoteModulation(Modulation):
    input: Literal[enums.Input.note, enums.Input.velocity]


class ControllerModulation(Modulation):
    input: Literal[enums.Input.controller]
    controller: MidiValue
    scope: Literal[enums.Scope.channel, enums.Scope.instrument] = enums.Scope.channel
    smoothing_seconds: Seconds = 0.005


class ChannelPressureModulation(Modulation):
    input: Literal[enums.Input.channel_pressure]
    scope: Literal[enums.Scope.channel, enums.Scope.instrument] = enums.Scope.channel
    smoothing_seconds: Seconds = 0.005


class NotePressureModulation(Modulation):
    input: Literal[enums.Input.note_pressure]
    scope: Literal[enums.Scope.note] = enums.Scope.note
    smoothing_seconds: Seconds = 0.005


class GeneratedModulation(Modulation):
    input: Literal[enums.Input.envelope, enums.Input.lfo]
    source: Identifier


class Crossfade(Model):
    input: enums.Input
    direction: enums.FadeDirection
    start: MidiValue
    end: MidiValue
    curve: enums.FadeCurve = enums.FadeCurve.linear

    @model_validator(mode='after')
    def valid_interval(self) -> Self:
        if self.input in (enums.Input.envelope, enums.Input.lfo):
            raise ValueError(
                'Crossfades require note, velocity, controller, or pressure input'
            )
        validate_input_value(self.input, self.start)
        validate_input_value(self.input, self.end)
        if self.start >= self.end:
            raise ValueError('Crossfade start must precede end')
        return self


class NoteCrossfade(Crossfade):
    input: Literal[enums.Input.note, enums.Input.velocity]


class ControllerCrossfade(Crossfade):
    input: Literal[enums.Input.controller]
    controller: MidiValue
    scope: Literal[enums.Scope.channel, enums.Scope.instrument] = enums.Scope.channel
    smoothing_seconds: Seconds = 0.005


class ChannelPressureCrossfade(Crossfade):
    input: Literal[enums.Input.channel_pressure]
    scope: Literal[enums.Scope.channel, enums.Scope.instrument] = enums.Scope.channel
    smoothing_seconds: Seconds = 0.005


class NotePressureCrossfade(Crossfade):
    input: Literal[enums.Input.note_pressure]
    scope: Literal[enums.Scope.note] = enums.Scope.note
    smoothing_seconds: Seconds = 0.005


def target_operation(target: str) -> enums.Operation:
    """Validate a target path independently of its containing processing scope."""
    if target in ('volume_db', 'tuning_cents', 'pan', 'stereo_balance'):
        return enums.Operation.add
    parts = target.split('.')
    if len(parts) == 3 and parts[0] == 'equalizer':
        if parts[2] == 'gain_db':
            return enums.Operation.add
        if parts[2] in ('frequency_hz', 'resonance'):
            return enums.Operation.multiply
    if (len(parts) == 2 and parts[0] == 'envelope') or (
        len(parts) == 3 and parts[0] == 'envelopes'
    ):
        if parts[-1] in ENVELOPE_DURATIONS:
            return enums.Operation.multiply
    raise ValueError(f'Unknown modulation target: {target}')


def validate_input_value(source: enums.Input, value: int | float) -> None:
    if source in (enums.Input.envelope, enums.Input.lfo):
        low, high = (-1, 1) if source == enums.Input.lfo else (0, 1)
    else:
        if not isinstance(value, int) or isinstance(value, bool):
            raise ValueError('MIDI input points must be integers')
        low, high = (1, 127) if source == enums.Input.velocity else (0, 127)
    if not low <= value <= high:
        raise ValueError(f'{source} input must be in [{low}, {high}]')


ModulationCurve = Annotated[
    NoteModulation
    | ControllerModulation
    | ChannelPressureModulation
    | NotePressureModulation
    | GeneratedModulation,
    Field(discriminator='input'),
]

LayerCrossfade = Annotated[
    NoteCrossfade
    | ControllerCrossfade
    | ChannelPressureCrossfade
    | NotePressureCrossfade,
    Field(discriminator='input'),
]

ENVELOPE_DURATIONS = (
    'delay_seconds',
    'attack_seconds',
    'hold_seconds',
    'decay_seconds',
    'release_seconds',
)
