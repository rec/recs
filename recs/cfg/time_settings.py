import dataclasses as dc
import math
import typing as t
from functools import cached_property

T = t.TypeVar('T', float, int)
NO_SCALE = ('noise_floor',)


def db_to_amplitude(db: float) -> float:
    return 10 ** (-db / 20)


def amplitude_to_db(amp: float) -> float:
    if amp > 0:
        return -20 * math.log10(amp)
    return float('inf')


@dc.dataclass(frozen=True)
class TimeSettings(t.Generic[T]):
    """Amounts of time are specified as seconds in the input but converted
    to samples when we find out the sample rate
    """

    #: Longest amount of time per file: 0 means infinite
    longest_file_time: T = t.cast(T, 0)

    #: Shortest amount of time per file
    shortest_file_time: T = t.cast(T, 0)

    #: Amount of quiet at the start
    quiet_before_start: T = t.cast(T, 0)

    #: Amount of quiet at the end
    quiet_after_end: T = t.cast(T, 0)

    #: Amount of quiet before stopping a recording
    stop_after_quiet: T = t.cast(T, 0)

    # Time for moving averages for the meters
    moving_average_time: T = t.cast(T, 0)

    #: The noise floor in decibels
    noise_floor: float = 70

    #: Amount of total time to run.  0 or less means "run forever"
    total_run_time: T = t.cast(T, 0)

    @cached_property
    def noise_floor_amplitude(self) -> float:
        return db_to_amplitude(self.noise_floor)

    def __post_init__(self):
        if negative_fields := [k for k, v in dc.asdict(self).items() if v < 0]:
            raise ValueError(f'TimeSettings cannot be negative: {negative_fields=}')

    def scale(self, samplerate: float | int) -> 'TimeSettings[int]':
        it = dc.asdict(self).items()
        d = {k: v if k in NO_SCALE else round(samplerate * v) for k, v in it}
        return TimeSettings[int](**d)
