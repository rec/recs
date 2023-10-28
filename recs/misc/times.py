import dataclasses as dc
import math
import typing as t
from functools import cached_property

T = t.TypeVar('T', float, int)

NO_SCALE = ('noise_floor',)


def db_to_amplitude(db: float) -> float:
    return 10 ** (-db / 20)


def amplitude_to_db(amp: float) -> float:
    return -20 * math.log10(amp)


@dc.dataclass(frozen=True)
class Times(t.Generic[T]):
    """Amounts of time are specified as seconds in the input but converted
    to samples when we find out the sample rate
    """

    #: Amount of silence at the start
    silence_before_start: T = t.cast(T, 0)

    #: Amount of silence at the end
    silence_after_end: T = t.cast(T, 0)

    #: Amount of silence before stopping a recording
    stop_after_silence: T = t.cast(T, 0)

    #: The noise floor in decibels
    noise_floor: float = 70

    #: Amount of total time to run.  0 or less means "run forever"
    total_run_time: T = t.cast(T, 0)

    @cached_property
    def noise_floor_amplitude(self) -> float:
        return db_to_amplitude(self.noise_floor)

    def __post_init__(self):
        if negative_fields := [k for k, v in dc.asdict(self).items() if v < 0]:
            raise ValueError(f'Times cannot be negative: {negative_fields=}')

    def scale(self, samplerate: float | int) -> 'Times[int]':
        it = dc.asdict(self).items()
        d = {k: v if k in NO_SCALE else round(samplerate * v) for k, v in it}
        return Times[int](**d)
