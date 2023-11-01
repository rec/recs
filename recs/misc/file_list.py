import os
from pathlib import Path


class FileList(list[Path]):
    """
    A list of paths with a total size. The size of the last file, only, in the list
    might be updated after it is added.
    """

    _count: int = 0
    _total_size: int = 0

    @property
    def total_size(self) -> int:
        if not self:
            return 0

        while self._count + 1 < len(self):
            self._total_size += os.path.getsize(self[self._count])
            self._count += 1

        return self._total_size + os.path.getsize(self[-1])
