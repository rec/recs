import time
import typing as t
from abc import ABC, abstractmethod
from functools import cached_property
from threading import Lock

from .mux import AudioUpdate


class HasRows(ABC):
    @abstractmethod
    def rows(self) -> t.Iterator[dict[str, t.Any]]:
        pass

    @abstractmethod
    def callback(self, u: AudioUpdate) -> None:
        pass


class Maker(HasRows, ABC):
    def __init__(self) -> None:
        self._lock = Lock()
        self.contents: t.Dict[str, HasRows] = {}

    def __post_init__(self):
        Maker.__init__(self)

    @cached_property
    def start_time(self):
        return time.time()

    @property
    def elapsed_time(self):
        return time.time() - self.start_time

    key_name: str

    @abstractmethod
    def make(self, u: AudioUpdate) -> HasRows:
        pass

    def rows(self) -> t.Iterator[dict[str, t.Any]]:
        for v in self.contents.values():
            yield from v.rows()

    def callback(self, u: AudioUpdate) -> None:
        name = getattr(u, self.key_name)

        with self._lock:
            try:
                has_rows = self.contents[name]
            except KeyError:
                self.contents[name] = has_rows = self.make(u)
        has_rows.callback(u)


class DeviceCallback(Maker):
    """This class gets callbacks from blocks from a single device"""

    key_name = 'channel_name'


class DevicesCallback(Maker):
    """This class gets callbacks from all blocks from all devices"""

    key_name = 'device_name'
