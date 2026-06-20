import math
import time

WINDOW_SECONDS = 2.0
SAMPLE_RATE = 1_000
FRAME_MS = 16
WINDOW_WIDTH = 960
WINDOW_HEIGHT = 540


class WaveformSource:
    def __init__(self) -> None:
        self.start_time = time.perf_counter()
        self.generated_until = 0.0
        self.times: list[float] = []
        self.samples: list[float] = []

    def read(self) -> tuple[list[float], list[float], float, float]:
        elapsed = time.perf_counter() - self.start_time
        self._append_until(elapsed)
        left = max(0.0, elapsed - WINDOW_SECONDS)
        right = left + WINDOW_SECONDS
        keep_from = left - 0.25
        keep = [
            (sample_time, sample)
            for sample_time, sample in zip(self.times, self.samples, strict=True)
            if sample_time >= keep_from
        ]
        self.times = [sample_time for sample_time, _ in keep]
        self.samples = [sample for _, sample in keep]
        visible = [
            (sample_time, sample)
            for sample_time, sample in zip(self.times, self.samples, strict=True)
            if left <= sample_time <= right
        ]
        return (
            [sample_time for sample_time, _ in visible],
            [sample for _, sample in visible],
            left,
            right,
        )

    def _append_until(self, elapsed: float) -> None:
        if elapsed <= self.generated_until:
            return

        sample_count = max(1, round((elapsed - self.generated_until) * SAMPLE_RATE))
        for index in range(sample_count):
            sample_time = self.generated_until + (index + 1) / SAMPLE_RATE
            self.times.append(sample_time)
            self.samples.append(_sample(sample_time))
        self.generated_until = self.times[-1]


def _sample(sample_time: float) -> float:
    fade_in = min(1.0, sample_time / 0.25)
    pulse = 0.25 * math.sin(sample_time * math.tau * 1.5)
    carrier = math.sin(sample_time * math.tau * (4.0 + pulse))
    overtone = 0.35 * math.sin(sample_time * math.tau * 11.0)
    return fade_in * (carrier + overtone) / 1.35
