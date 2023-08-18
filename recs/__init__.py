import dataclasses as dc
import typing as t

import numpy as np

DType = np.float32
Array = np.ndarray


def field(default_factory: t.Optional[t.Callable[[], t.Any]] = None, **ka):
    if default_factory is not None:
        ka['default_factory'] = default_factory
    return dc.field(**ka)
