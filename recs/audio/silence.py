import dataclasses as dc
import typing as t
from functools import cached_property

T = t.TypeVar('T', float, int)


@dc.dataclass(frozen=True)
class SilenceStrategy(t.Generic[T]):
    """Amounts of time are specified as seconds in the input but converted
    to samples when we find out the sample rate
    """

    #: Amount of silence at the start
    before_start: T

    #: Amount of silence at the end
    after_end: T

    #: Amount of silence before stopping a recording
    stop_after: T

    #: The noise floor in decibels
    noise_floor: float = 70

    @cached_property
    def noise_floor_amplitude(self):
        return 10 ** (-self.noise_floor / 10)


def scale(source: SilenceStrategy[float], sample_rate: float) -> SilenceStrategy[int]:
    return SilenceStrategy[int](
        before_start=round(sample_rate * source.before_start),
        after_end=round(sample_rate * source.after_end),
        stop_after=round(sample_rate * source.stop_after),
        noise_floor=source.noise_floor,
    )
