from collections.abc import Callable
from enum import StrEnum, auto

Stop = Callable[[], None]


class Mutable:
    pass


class Active(StrEnum):
    active = auto()
    inactive = auto()
    offline = auto()


class RecordKeys(StrEnum):
    none = auto()
    press = auto()
    all = auto()


class MidiTiming(StrEnum):
    mido = auto()
    system = auto()


class SdType(StrEnum):
    float32 = auto()
    int16 = auto()
    int32 = auto()


SDTYPE = SdType.float32
