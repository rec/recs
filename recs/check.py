from . import device, mux
import contextlib
import dataclasses as dc


DEVICE_SLICES = {
    'FLOW': mux.auto_slice(8) | {'Main': slice(8, 10)}
}


class Checker:
    def __call__(self, frame, channel_name, device):
        pass


def check():
    devices = device.input_devices()
    slices = mux.slice_all(devices.values(), DEVICE_SLICES)
    import pprint
    pprint.pprint(slices)
