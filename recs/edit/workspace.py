"""Invocation-local scratch placement and conservative free-space checks."""

import shutil
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path

from ..base.errors import RecsError


@contextmanager
def audio_workspace(directory: Path | None) -> Iterator[None]:
    path = (directory or Path(tempfile.gettempdir())).resolve()
    if not path.is_dir():
        raise RecsError(f'Scratch directory must already exist: {path}')
    token = SCRATCH_DIRECTORY.set(path)
    try:
        yield
    finally:
        SCRATCH_DIRECTORY.reset(token)


def check_space(
    scratch_bytes: int,
    destination: Path,
    destination_bytes: int,
    scratch: Path | None = None,
) -> None:
    scratch = scratch or SCRATCH_DIRECTORY.get() or Path(tempfile.gettempdir())
    target = destination.resolve()
    while not target.exists():
        target = target.parent
    required = {scratch: scratch_bytes}
    if scratch.stat().st_dev == target.stat().st_dev:
        required[scratch] += destination_bytes
    else:
        required[target] = destination_bytes
    for path, size in required.items():
        free = shutil.disk_usage(path).free
        if size > free:
            raise RecsError(
                f'Insufficient space at {path}: need {size} bytes, have {free}'
            )


SCRATCH_DIRECTORY: ContextVar[Path | None] = ContextVar(
    'recs_audio_scratch', default=None
)
