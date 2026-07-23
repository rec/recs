import os

from recs.base import RecsError

ROOT_DAEMON_ERROR = 'recs daemon must not run as root'


def raise_if_root() -> None:
    if is_root():
        raise RecsError(ROOT_DAEMON_ERROR)


def is_root() -> bool:
    getuid = getattr(os, 'geteuid', None) or getattr(os, 'getuid', None)
    return callable(getuid) and getuid() == 0
