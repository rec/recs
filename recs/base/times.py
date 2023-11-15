import dataclasses as dc
import math
import time as _time
import typing as t
from functools import cached_property

T = t.TypeVar('T', float, int)
NO_SCALE = ('noise_floor',)

sleep = _time.sleep
time = _time.time


def db_to_amplitude(db: float) -> float:
    return 10 ** (-db / 20)


def amplitude_to_db(amp: float) -> float:
    return -20 * math.log10(amp)


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


def to_time(t: str) -> float:
    parts = t.split(':')
    if not (1 <= len(parts) <= 3):
        raise ValueError('A time can only have three parts')

    s = float(parts.pop())
    if s < 0:
        raise ValueError('TimeSettings cannot be negative')

    if not parts:
        return s

    if s > 59:
        raise ValueError('Seconds cannot be greater than 59')

    m = int(parts.pop())
    if m < 0:
        raise ValueError('Minutes cannot be negative')

    s += 60 * m
    if not parts:
        return s

    if m > 59:
        raise ValueError('Minutes cannot be greater than 59')

    h = int(parts.pop())
    if h < 0:
        raise ValueError('Hours cannot be negative')

    assert not parts
    return s + 3600 * h


def to_str(dt: float | int) -> str:
    m, s = divmod(dt, 60)
    m = int(m)
    h, m = divmod(m, 60)
    t = f'{s:06.3f}'
    if h:
        return f'{h}:{m:02}:{t}'
    if m:
        return f'{m}:{t}'
    return f'{s:.3f}'
