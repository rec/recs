import dataclasses as dc
import time
import typing as t
from threading import Lock

from recs import field

from .mux import AudioUpdate


class Maker:
    Class: t.ClassVar[t.Type]
    contents: t.Dict[str, t.Any]

    def __init__(self):
        self._lock = Lock()
        self.contents = {}

    def __post_init__(self):
        Maker.__init__(self)

    def get(self, name: str, value: t.Any):
        with self._lock:
            try:
                return self.contents[name]
            except KeyError:
                pass
            self.contents[name] = ch = self.Class()
            return ch


@dc.dataclass
class ChannelCallback:
    """This class gets callbacks from blocks from a channel within a device"""

    def callback(self, u: AudioUpdate):
        raise NotImplementedError


class DeviceCallback(Maker):
    """This class gets callbacks from blocks from a single device"""

    Class = ChannelCallback

    def callback(self, u: AudioUpdate) -> None:
        self.get(u.channel_name, u.device).callback(u)


@dc.dataclass
class DevicesCallback(Maker):
    """This class gets callbacks from all blocks from all devices"""

    start_time: float = field(time.time)

    Class = DeviceCallback

    @property
    def elapsed_time(self):
        return time.time() - self.start_time

    def callback(self, u: AudioUpdate):
        self.get(u.device.name, u.device).callback(u)
