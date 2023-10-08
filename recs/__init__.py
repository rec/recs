import dataclasses as dc
import functools
import typing as t

import numpy as np

DType = np.float32
Array = np.ndarray
array = functools.partial(np.array, dtype=DType)

PART_SPLITTER = '+'


def split(s: str, splitter: str = PART_SPLITTER) -> list[str]:
    return [i.strip() for i in s.split(splitter)]


def field(default_factory: t.Optional[t.Callable[[], t.Any]] = None, **ka):
    if default_factory is not None:
        ka['default_factory'] = default_factory
    return dc.field(**ka)


class RecsError(ValueError):
    pass
