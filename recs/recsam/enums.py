"""Names serialized in recsam TOML documents."""

from enum import auto

from strenum import StrEnum


class Direction(StrEnum):
    forward = auto()
    backward = auto()
    mirror = auto()


class PlaybackMode(StrEnum):
    while_held = auto()
    one_shot = auto()


class LoopMode(StrEnum):
    until_release = auto()
    through_release = auto()


class TriggerKind(StrEnum):
    start = auto()
    release = auto()
    logical_release = auto()
    sustain_press = auto()
    sustain_release = auto()


class SelectionMode(StrEnum):
    cycle = auto()
    random = auto()
    shuffle = auto()


class ChokeMode(StrEnum):
    immediate = auto()
    fade = auto()
    release = auto()


class KeyBehavior(StrEnum):
    latched = auto()
    momentary = auto()


class EnvelopeShape(StrEnum):
    linear = auto()
    exponential = auto()


class Waveform(StrEnum):
    sine = auto()
    triangle = auto()


class Scope(StrEnum):
    instrument = auto()
    part = auto()
    trigger = auto()
    voice = auto()


class Input(StrEnum):
    key = auto()
    velocity = auto()
    control = auto()
    envelope = auto()
    lfo = auto()


class Polarity(StrEnum):
    unipolar = auto()
    bipolar = auto()


class Operation(StrEnum):
    add = auto()
    multiply = auto()


class Interpolation(StrEnum):
    linear = auto()
    step = auto()


class FadeDirection(StrEnum):
    fade_in = 'in'
    fade_out = 'out'


class FadeCurve(StrEnum):
    linear = auto()
    equal_power = auto()
