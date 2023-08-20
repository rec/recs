import dataclasses as dc
import typing as t
from functools import cached_property

T = t.TypeVar('T', int, float)


@dc.dataclass(frozen=True)
class SilenceStrategy(t.Generic[T]):
    """Amounts of time are specified as seconds in the input but converted
    to samples when we find out the sample rate
    """

    #: Amount of silence at the start
    at_start: T

    #: Amount of silence at the end
    at_end: T

    #: Amount of silence before stopping a recording
    before_stopping: T

    #: The noise floor in decibels
    noise_floor_db: float = 70

    @cached_property
    def noise_floor(self):
        return 10 ** (-self.noise_floor_db / 10)


def scale(source: SilenceStrategy[float], sample_rate: float) -> SilenceStrategy[int]:
    return SilenceStrategy[int](
        at_start=round(sample_rate * source.at_start),
        at_end=round(sample_rate * source.at_end),
        before_stopping=round(sample_rate * source.before_stopping),
        noise_floor_db=source.noise_floor_db,
    )
