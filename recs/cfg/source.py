import abc
from collections.abc import Callable
from typing import NamedTuple

import numpy as np
from threa import Runnable

from recs.base.types import Format, SdType, Subtype
from recs.cfg import hash_cmp


def to_matrix(array: np.ndarray) -> np.ndarray:
    return array.reshape(*array.shape, 1) if len(array.shape) == 1 else array


class Update(NamedTuple):
    array: np.ndarray
    timestamp: float
    status: str = ''


class Source(hash_cmp.HashCmp, abc.ABC):
    def __init__(
        self,
        channels: int,
        name: str,
        samplerate: int,
        format: Format | None = None,
        subtype: Subtype | None = None,
    ) -> None:
        self._key = self.name = name
        self.channels = channels
        self.format = format
        self.samplerate = samplerate
        self.subtype = subtype

    def __str__(self) -> str:
        return self.name

    @abc.abstractmethod
    def input_stream(
        self, sdtype: SdType, update_callback: Callable[[Update], None]
    ) -> Runnable:
        pass
