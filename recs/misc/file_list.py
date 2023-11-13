import os
from pathlib import Path


class FileList(list[Path]):
    """
    A list of paths with a total size. The size of the last file, only, in the list
    might be updated after it is added.  Missing files are not reported and count
    as zero bytes.
    """

    _count: int = 0
    _total_size: int = 0

    @property
    def total_size(self) -> int:
        if not self:
            return 0

        while self._count + 1 < len(self):
            self._total_size += _getsize(self[self._count])
            self._count += 1

        return self._total_size + _getsize(self[-1])


def _getsize(p) -> int:
    try:
        return os.path.getsize(p)
    except FileNotFoundError:
        return 0
