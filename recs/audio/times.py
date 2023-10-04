import dataclasses as dc
import typing as t
from functools import cached_property

T = t.TypeVar('T', float, int)

NO_SCALE = ('noise_floor',)


@dc.dataclass(frozen=True)
class Times(t.Generic[T]):
    """Amounts of time are specified as seconds in the input but converted
    to samples when we find out the sample rate
    """

    #: Amount of silence at the start
    silence_before_start: T

    #: Amount of silence at the end
    silence_after_end: T

    #: Amount of silence before stopping a recording
    stop_after_silence: T

    #: The noise floor in decibels
    noise_floor: float = 70

    #: Amount of total time to run.  0 or less means "run forever"
    total_run_time: T = t.cast(T, 0)

    @cached_property
    def noise_floor_amplitude(self):
        return 10 ** (-self.noise_floor / 10)


def scale(source: Times[float], samplerate: float) -> Times[int]:
    it = dc.asdict(source).items()
    d = {k: v if k in NO_SCALE else round(samplerate * v) for k, v in it}
    return Times[int](**d)
