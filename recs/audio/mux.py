import contextlib
import dataclasses as dc
import typing as t

import sounddevice as sd

from recs import Array
from recs.audio.block import Block
from recs.audio.device import InputDevice
from recs.util.slicer import Slices, SlicesDict, slice_device

Stop = t.Callable[[], None]


@dc.dataclass(frozen=True)
class AudioUpdate:
    device: InputDevice
    block: Block
    channel_name: str


ChannelCallback = t.Callable[[AudioUpdate], None]


@dc.dataclass(frozen=True)
class DemuxContext:
    devices: t.Sequence[InputDevice]
    callback: ChannelCallback
    stop: Stop
    device_slices: SlicesDict

    @contextlib.contextmanager
    def __call__(self) -> t.Iterator[sd.InputStream]:
        streams = [self._input_stream(d) for d in self.devices]
        with contextlib.ExitStack() as stack:
            [stack.enter_context(s) for s in streams]
            yield streams

    def _input_stream(self, device: InputDevice) -> sd.InputStream:
        slices = slice_device(device, self.device_slices)
        demux = _Demuxer(self.callback, slices)
        return device.input_stream(demux, self.stop)


@dc.dataclass(frozen=True)
class _Demuxer:
    callback: ChannelCallback
    slices: Slices

    def __call__(self, array: Array, device: InputDevice):
        for k, v in self.slices.items():
            self.callback(AudioUpdate(device, Block(array[:, v]), k))
