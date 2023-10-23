import dataclasses as dc
import numbers
from threading import Lock

import numpy as np

# TODO: isn't there some type comprising these first four?
Num = int | float | numbers.Integral | numbers.Real | np.ndarray


@dc.dataclass
class Counter:
    value: int = 0
    lock: Lock = dc.field(default_factory=Lock)

    def __call__(self, i: int = 1) -> int:
        with self.lock:
            self.value += i
            return self.value


class Accumulator:
    count: int = 0
    value: Num = 0
    sum: Num
    square_sum: Num

    def __call__(self, x: Num) -> None:
        self.value = x
        self.count += 1
        try:
            self.sum += x
        except AttributeError:
            self.sum = x.copy() if isinstance(x, np.ndarray) else x
            self.square_sum = x * x
        else:
            self.square_sum += x * x

    def mean(self) -> Num:
        return self.count and self.sum / self.count

    def stdev(self) -> Num:
        return self.variance() ** 0.5

    def variance(self) -> Num:
        return self.count and self.square_sum / self.count
