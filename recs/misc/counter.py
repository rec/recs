import dataclasses as dc
import numbers
import typing as t
from collections import deque
from threading import Lock

import numpy as np

from recs.audio.block import Block

# TODO: isn't there some type comprising these first four?
Num: t.TypeAlias = int | float | numbers.Integral | numbers.Real | np.ndarray


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
        try:
            self.sum += x
        except AttributeError:
            self.sum = x.copy() if isinstance(x, np.ndarray) else x
            self.square_sum = x * x
        else:
            self.square_sum += x * x
        self.count += 1

    def mean(self) -> Num:
        return self.count and self.sum / self.count

    def stdev(self) -> Num:
        return self.variance() ** 0.5

    def variance(self) -> Num:
        return self.count and self.square_sum / self.count


class MovingBlock:
    _dq: deque[np.ndarray] | None = None

    def __init__(self, moving_average_time: int):
        self.moving_average_time = moving_average_time

    def __call__(self, b: Block) -> None:
        if self._dq is None:
            maxlen = int(0.5 + self.moving_average_time / len(b))
            self._dq = deque((), maxlen)

        self._dq.append(b.amplitude)

    def mean(self) -> np.ndarray:
        if not self._dq:
            return np.array([0])

        it = (d for i, d in enumerate(self._dq) if i)
        return sum(it, start=self._dq[0]) / len(self._dq)
