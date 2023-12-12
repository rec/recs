import os
import typing as t
from functools import cache, wraps

C = t.TypeVar('C', bound=t.Callable)

DISABLE = False

# Some sort of global state is needed here so that we can decorate
# methods without having to have a Cfg around.
VERBOSE = not False


@cache
def _logger():
    return open(f'/tmp/log-{os.getpid()}.txt', 'w')


def log(*a, **ka) -> None:
    print(*a, **ka, file=_logger())


def verbose(*a, **ka) -> None:
    if VERBOSE:
        log(*a, **ka)


def logged(function: C) -> C:
    if DISABLE:
        return function

    @wraps(function)
    def wrapped(*args, **kwargs):
        verbose(function, 'before')
        try:
            return function(*args, **kwargs)
        except BaseException as e:
            verbose(function, 'exception', type(e), *e.args)
            raise
        finally:
            verbose(function, 'after')

    return t.cast(C, wrapped)
