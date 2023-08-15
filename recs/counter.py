import dataclasses as dc
import math
from threading import Lock


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
    sum: float = 0
    square_sum: float = 0
    last: float = 0

    def accum(self, x: float):
        self.last = x
        self.count += 1
        self.sum += x
        self.square_sum += x * x

    def mean(self) -> float:
        return self.count and self.sum / self.count

    def stdev(self) -> float:
        return math.sqrt(self.variance())

    def variance(self) -> float:
        return self.count and self.square_sum / self.count
