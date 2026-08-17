import os
import time
from pathlib import Path

ACTIVE_SIZE_CACHE_SECONDS = 1.0


class FileList(list[Path]):
    """
    A list of paths with a total size. The size of the last file, only, in the list
    might be updated after it is added.  Missing files are not reported and count
    as zero bytes.
    """

    _count: int = 0
    _total_size: int = 0
    _last_size_path: Path | None = None
    _last_size_time: float = float('-inf')
    _last_size: int = 0

    @property
    def total_size(self) -> int:
        if not self:
            return 0

        while self._count + 1 < len(self):
            self._total_size += _getsize(self[self._count])
            self._count += 1

        return self._total_size + _getsize(self[-1])

    @property
    def cached_total_size(self) -> int:
        if not self:
            return 0

        while self._count + 1 < len(self):
            self._total_size += _getsize(self[self._count])
            self._count += 1

        now = time.monotonic()
        path = self[-1]
        if (
            path != self._last_size_path
            or now - self._last_size_time >= ACTIVE_SIZE_CACHE_SECONDS
        ):
            self._last_size_path = path
            self._last_size_time = now
            self._last_size = _getsize(path)
        return self._total_size + self._last_size

    def remove_path(self, path: Path) -> None:
        self[:] = [p for p in self if p != path]
        self._count = 0
        self._total_size = 0
        self._last_size_path = None
        self._last_size_time = float('-inf')
        self._last_size = 0


def _getsize(p: Path) -> int:
    try:
        return os.path.getsize(p)
    except FileNotFoundError:
        return 0
