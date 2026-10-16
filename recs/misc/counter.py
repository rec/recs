from collections import deque

import numpy as np

from recs.audio.block import Block


class MovingBlock:
    _dq: deque[np.ndarray] | None = None

    def __init__(self, moving_average_time: int) -> None:
        self.moving_average_time = moving_average_time
        self._sum: np.ndarray | None = None

    def accumulate(self, b: Block) -> None:
        if self._dq is None:
            maxlen = int(0.5 + self.moving_average_time / len(b))
            self._dq = deque((), maxlen)

        if not self._dq.maxlen:
            return
        if self._sum is None:
            self._sum = np.zeros_like(b.amplitude, dtype=np.float64)
        elif len(self._dq) == self._dq.maxlen:
            self._sum -= self._dq[0]
        self._dq.append(b.amplitude)
        self._sum += b.amplitude

    def mean(self) -> np.ndarray:
        if not self._dq:
            return np.array([0])

        assert self._sum is not None
        return self._sum / len(self._dq)
