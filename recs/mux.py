from . import Array
import dataclasses as dc
import typing as t
import contextlib


SliceDict = t.Dict[str, slice]


@dc.dataclass(frozen=True)
class Demuxer:
    callback: t.Callable
    slices: t.Dict[str, slice]

    def __call__(self, frame: Array, *args):
        for k, v in self.slices.items():
            self.callback(k, frame[:, v], *args)


def auto_slice(channels: int) -> SliceDict:
    def slicer():
        # Display channnels start at channel 1, not 0
        for i in range(0, channels - 1, 2):
            yield f'{i + 1}-{i + 2}', slice(i, i + 2)
        if channels % 1:
            yield f'{channels}', slice(channels, channels + 1)

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


def demux_one(device, callback, device_slices: t.Dict[str, SliceDict]):
    m = [v for k, v in device_slices.items() if device.name.startswith(k)]
    slices = to_slices(m[0]) if m else auto_slice(device.channels)
    demux = Demuxer(callback, slices)
    return device.input_stream(demux)


@contextlib.contextmanager
def demux_context(devices, callback, device_slices: t.Dict[str, SliceDict]):
    streams = [demux_one(d, callback, device_slices) for d in devices]
    with contextlib.ExitStack() as stack:
        [stack.enter_context(s) for s in streams]
        yield streams