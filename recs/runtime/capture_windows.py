from collections.abc import Iterator
from time import monotonic

import numpy as np

from recs.cfg.source import Update

from .input_buffer import BufferedUpdate


class CaptureWindows:
    """Consumer-owned sample windows, independent of driver callback boundaries."""

    def __init__(
        self, sample_rate: int, window_seconds: float, maximum_wait_seconds: float
    ) -> None:
        self.sample_rate = sample_rate
        self.window_frames = max(2, round(sample_rate * window_seconds))
        self.maximum_wait_seconds = maximum_wait_seconds
        self.array: np.ndarray | None = None
        self.count = 0
        self.start_frame = 0
        self.timestamp = 0.0
        self.status = ''
        self.uncertain = False
        self.deadline = 0.0
        self.expected_frame: int | None = None

    @property
    def expired(self) -> bool:
        return bool(self.count and monotonic() >= self.deadline)

    @property
    def wait_seconds(self) -> float:
        return (
            max(0.0, self.deadline - monotonic())
            if self.count
            else self.maximum_wait_seconds
        )

    def receive(self, buffered: BufferedUpdate) -> Iterator[BufferedUpdate]:
        update = buffered.update
        gap = (
            self.expected_frame is not None
            and buffered.start_frame != self.expected_frame
        )
        if gap or update.status:
            if (pending := self.flush()) is not None:
                yield pending
        offset = 0
        status = update.status
        while offset < len(update.array):
            if self.array is None:
                self.start_frame = buffered.start_frame + offset
                self.timestamp = update.timestamp + offset / self.sample_rate
                self.deadline = monotonic() + self.maximum_wait_seconds
                self.array = np.empty(
                    (
                        self.window_frames - self.start_frame % self.window_frames,
                        *update.array.shape[1:],
                    ),
                    dtype=update.array.dtype,
                )
                self.uncertain = (
                    gap
                    or buffered.uncertain
                    or self.start_frame % self.window_frames != 0
                )
                gap = False
            if status:
                self.status = status
                status = ''
            count = min(len(update.array) - offset, len(self.array) - self.count)
            self.array[self.count : self.count + count] = update.array[
                offset : offset + count
            ]
            self.count += count
            offset += count
            if self.count == len(self.array):
                window = self._take()
                yield window
        self.expected_frame = buffered.end_frame

    def flush(self) -> BufferedUpdate | None:
        if not self.count:
            return None
        self.uncertain = True
        return self._take()

    def _take(self) -> BufferedUpdate:
        assert self.array is not None
        result = BufferedUpdate(
            Update(self.array[: self.count], self.timestamp, self.status),
            self.start_frame,
            self.start_frame + self.count,
            self.uncertain,
        )
        self.array = None
        self.count = 0
        self.status = ''
        self.uncertain = False
        return result
