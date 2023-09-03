import dataclasses as dc
import typing as t

from . import field
from .block import Block
from .device import InputDevice


@dc.dataclass
class Channel:
    channel_name: str
    device: InputDevice

    def callback(self, block: Block):
        raise NotImplementedError


@dc.dataclass
class Device:
    device: InputDevice
    channels: dict[str, Channel] = field(dict)

    Channel: t.ClassVar[t.Type]

    def callback(self, block: Block, channel_name: str):
        try:
            ch = self.channels[channel_name]
        except KeyError:
            ch = self.channels[channel_name] = self.Channel(channel_name, self.device)
        ch.callback(block)


@dc.dataclass
class Top:
    devices: dict = field(dict)

    Device: t.ClassVar[t.Type]

    def callback(self, block: Block, channel_name: str, device: InputDevice):
        try:
            dev = self.devices[device.name]
        except KeyError:
            dev = self.devices[device.name] = self.Device(device)
        dev.callback(block, channel_name)
