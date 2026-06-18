import typing as t
from collections import deque

import numpy as np

from recs.audio.block import Block

class MovingBlock:
    _dq: deque[np.ndarray] | None = None

    def __init__(self, moving_average_time: int):
        self.moving_average_time = moving_average_time

    def accumulate(self, b: Block) -> None:
        if self._dq is None:
            maxlen = int(0.5 + self.moving_average_time / len(b))
            self._dq = deque((), maxlen)

        self._dq.append(b.amplitude)

    def mean(self) -> np.ndarray:
        if not self._dq:
            return np.array([0])

        it = (d for i, d in enumerate(self._dq) if i)
        return sum(it, start=self._dq[0]) / len(self._dq)
