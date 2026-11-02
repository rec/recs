import os
import sys
from collections.abc import Iterable
from pathlib import Path

import numpy as np


def available_bytes() -> int | None:
    if (available := _linux_available_bytes()) is not None:
        return available
    try:
        return os.sysconf('SC_AVPHYS_PAGES') * os.sysconf('SC_PAGE_SIZE')
    except (AttributeError, OSError, ValueError):
        return None


def array_owners_bytes(arrays: Iterable[np.ndarray]) -> int:
    """Count each retained NumPy backing allocation once, including array headers."""
    owners: dict[int, np.ndarray] = {}
    for array in arrays:
        owner = array
        while isinstance(owner.base, np.ndarray):
            owner = owner.base
        owners[id(owner)] = owner
    return sum(
        sys.getsizeof(a) + (a.nbytes if a.base is not None else 0)
        for a in owners.values()
    )


def _linux_available_bytes() -> int | None:
    try:
        lines = Path('/proc/meminfo').read_text().splitlines()
    except (OSError, ValueError):
        return None
    for line in lines:
        if line.startswith('MemAvailable:'):
            return int(line.split()[1]) * 1_024
    return None
