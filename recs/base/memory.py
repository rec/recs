import os
from pathlib import Path


def available_bytes() -> int | None:
    if (available := _linux_available_bytes()) is not None:
        return available
    try:
        return os.sysconf('SC_AVPHYS_PAGES') * os.sysconf('SC_PAGE_SIZE')
    except (AttributeError, OSError, ValueError):
        return None


def _linux_available_bytes() -> int | None:
    try:
        lines = Path('/proc/meminfo').read_text().splitlines()
    except (OSError, ValueError):
        return None
    for line in lines:
        if line.startswith('MemAvailable:'):
            return int(line.split()[1]) * 1_024
    return None
