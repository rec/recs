import contextlib
import dataclasses as dc
import typing as t

from . import Array

SliceDict = t.Dict[str, slice]


@dc.dataclass(frozen=True)
class Demuxer:
    callback: t.Callable
    slices: t.Dict[str, slice]

    def __call__(self, frame: Array, *args):
        for k, v in self.slices.items():
            self.callback(frame[:, v], k, *args)


def auto_slice(channels: int) -> SliceDict:
    def slicer():
        # Display channnels start at channel 1, not 0
        for i in range(0, channels - 1, 2):
            yield f'{i + 1}-{i + 2}', slice(i, i + 2)
        if channels % 2:
            yield f'{channels}', slice(channels - 1, channels)

    return dict(slicer())


def to_slice(x):
    if isinstance(x, slice):
        return x
    try:
        return slice(**x)
    except TypeError:
        return slice(*x)


def to_slices(d):
    return {k: to_slice(v) for k, v in d.items()}


def slice_one(device, device_slices):
    name = device.name.lower()
    m = [v for k, v in device_slices.items() if name.startswith(k.lower())]
    return to_slices(m[0]) if m else auto_slice(device.channels)


def slice_all(devices, device_slices):
    return {d.name: slice_one(d, device_slices) for d in devices}


def input_stream(device, callback, stop, device_slices: t.Dict[str, SliceDict]):
    slices = slice_one(device, device_slices)
    demux = Demuxer(callback, slices)
    return device.input_stream(demux, stop)


@contextlib.contextmanager
def demux_context(devices, callback, stop, device_slices: t.Dict[str, SliceDict]):
    streams = [input_stream(d, callback, stop, device_slices) for d in devices]
    with contextlib.ExitStack() as stack:
        [stack.enter_context(s) for s in streams]
        yield streams
