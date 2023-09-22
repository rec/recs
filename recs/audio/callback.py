import dataclasses as dc
import time
import typing as t
from threading import Lock

from recs import field
from recs.audio.device import InputDevice

from .block import Block


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
            self.contents[name] = ch = self.Class(name, value)
            return ch


@dc.dataclass
class ChannelCallback:
    """This class gets callbacks from blocks from a channel within a device"""

    channel_name: str
    device: InputDevice

    def callback(self, block: Block):
        raise NotImplementedError


@dc.dataclass
class DeviceCallback(Maker):
    """This class gets callbacks from blocks from a single device"""

    device_name: str
    device: InputDevice

    Class = ChannelCallback

    def callback(self, block: Block, channel_name: str) -> None:
        self.get(channel_name, self.device).callback(block)


@dc.dataclass
class DevicesCallback(Maker):
    """This class gets callbacks from all blocks from all devices"""

    start_time: float = field(time.time)

    Class = DeviceCallback

    @property
    def elapsed_time(self):
        return time.time() - self.start_time

    def callback(self, block: Block, channel_name: str, device: InputDevice):
        self.get(device.name, device).callback(block, channel_name)
