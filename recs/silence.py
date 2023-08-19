import dataclasses as dc
from functools import cached_property


@dc.dataclass
class SilenceStrategy:
    at_start: int
    at_end: int
    before_splitting: int
    noise_floor_db: float = 70
    sample_range: int = 0x1_0000_0000

    @cached_property
    def noise_floor(self):
        ratio = 10 ** (self.noise_floor_db / 10)
        return self.sample_range // ratio
