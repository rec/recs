import contextlib
import dataclasses as dc
import typing as t

import sounddevice as sd

from recs.util.slicer import Slices, SlicesDict, slice_one
from recs.util.types import Array, Block, Callback, InputDevice, InputDevices, Stop


@dc.dataclass(frozen=True)
class Demuxer:
    callback: Callback
    slices: Slices

    def __call__(self, frame: Array, *args):
        for k, v in self.slices.items():
            self.callback(Block(frame[:, v]), k, *args)


def input_stream(
    device: InputDevice, callback: Callback, stop: Stop, device_slices: SlicesDict
) -> sd.InputStream:
    slices = slice_one(device, device_slices)
    demux = Demuxer(callback, slices)
    return device.input_stream(demux, stop)


@contextlib.contextmanager
def demux_context(
    devices: InputDevices,
    callback: Callback,
    stop: Stop,
    device_slices: SlicesDict,
) -> t.Iterator[sd.InputStream]:
    streams = [input_stream(d, callback, stop, device_slices) for d in devices]
    with contextlib.ExitStack() as stack:
        [stack.enter_context(s) for s in streams]
        yield streams
