import typing as t

from recs.audio.device import InputDevice
from recs.audio.prefix_dict import PrefixDict

__all__ = 'auto_slice', 'slice_device'

SlicesDict = PrefixDict[dict[str, slice]]


def slice_device(device: InputDevice, device_slices: SlicesDict) -> dict[str, slice]:
    try:
        m = device_slices[device.name]
    except KeyError:
        return auto_slice(device.channels)
    return _to_slices(m)


def auto_slice(channels: int) -> dict[str, slice]:
    def slicer() -> t.Iterator[tuple[str, slice]]:
        # Display channnels start at channel 1, not 0
        for i in range(0, channels - 1, 2):
            yield f'{i + 1}-{i + 2}', slice(i, i + 2)
        if channels % 2:
            yield f'{channels}', slice(channels - 1, channels)

    return dict(slicer())


def _to_slice(x: slice | dict[str, int] | t.Sequence) -> slice:
    if isinstance(x, slice):
        return x

    if not isinstance(x, dict):
        return slice(*x)

    d = dict(x)
    start = d.pop('start', 0)
    stop = d.pop('stop', None)
    step = d.pop('step', 1)

    assert stop is not None
    assert not d, f'Additional entries {d}'

    return slice(start, stop, step)


def _to_slices(d: dict) -> dict[str, slice]:
    return {k: _to_slice(v) for k, v in d.items()}
