import dataclasses as dc
import numpy as np
from threading import Lock

Num = float | np.ndarray


@dc.dataclass
class Counter:
    value: int = 0
    lock: Lock = dc.field(default_factory=Lock)

    def increment(self, i: int = 1) -> int:
        with self.lock:
            self.value += i
            return self.value


class Accumulator:
    count: int = 0
    last: Num
    sum: Num
    square_sum: Num

    def accum(self, x: float | np.ndarray):
        self.last = x
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
