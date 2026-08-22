import shutil
from collections import deque
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Threshold:
    bytes: int | None = None
    seconds: float | None = None

    def required_bytes(self, write_rate: float) -> int:
        values = [
            value
            for value in (self.bytes, _rate_bytes(self.seconds, write_rate))
            if value
        ]
        return max(values, default=0)


@dataclass(frozen=True)
class Disk:
    path: Path
    free_bytes: int
    total_bytes: int
    removable: bool


class WriteRate:
    def __init__(self, window: float = 60) -> None:
        self.window = window
        self.samples: deque[tuple[float, int]] = deque()

    def add(self, timestamp: float, used_bytes: int) -> None:
        self.samples.append((timestamp, used_bytes))
        while self.samples and timestamp - self.samples[0][0] > self.window:
            self.samples.popleft()

    @property
    def bytes_per_second(self) -> float:
        if len(self.samples) < 2:
            return 0
        start, end = self.samples[0], self.samples[-1]
        elapsed = end[0] - start[0]
        return max(0, (end[1] - start[1]) / elapsed) if elapsed else 0


def parse_threshold(value: str) -> Threshold:
    normalized = value.strip().lower()
    for suffix, multiplier in (
        ('gb', 1_000_000_000),
        ('mb', 1_000_000),
        ('kb', 1_000),
    ):
        if normalized.endswith(suffix):
            return Threshold(
                bytes=round(float(normalized.removesuffix(suffix)) * multiplier)
            )
    for suffix, multiplier in (('h', 3600), ('m', 60), ('s', 1)):
        if normalized.endswith(suffix):
            return Threshold(
                seconds=float(normalized.removesuffix(suffix)) * multiplier
            )
    return Threshold(bytes=int(normalized))


def threshold_bytes(values: Iterable[str], write_rate: float) -> int:
    return max(
        (parse_threshold(value).required_bytes(write_rate) for value in values),
        default=0,
    )


def free_space(value: int) -> str:
    if value >= 1_000_000_000:
        return f'{value / 1_000_000_000:.1f} G'
    return f'{value / 1_000_000:.1f} M'


def disk(path: Path, removable: bool) -> Disk | None:
    try:
        usage = shutil.disk_usage(path)
    except OSError:
        return None
    return Disk(
        path=path, free_bytes=usage.free, total_bytes=usage.total, removable=removable
    )


def _rate_bytes(seconds: float | None, write_rate: float) -> int | None:
    return round(seconds * write_rate) if seconds is not None else None
