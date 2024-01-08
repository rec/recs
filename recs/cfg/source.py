import abc
import typing as t

import numpy as np
from threa import Runnable

from recs.base.types import Stop, SdType
from recs.cfg import hash_cmp


class Update(t.NamedTuple):
    array: np.ndarray
    timestamp: float


class Source(hash_cmp.HashCmp, abc.ABC):
    def __init__(self, channels: int, name: str, samplerate: float) -> None:
        self._key = self.name = name
        self.channels = channels
        self.samplerate = samplerate

    def __str__(self) -> str:
        return self.name

    @abc.abstractmethod
    def input_stream(
        self,
        on_error: Stop,
        sdtype: SdType,
        update_callback: t.Callable[[Update], None],
    ) -> Runnable:
        pass
