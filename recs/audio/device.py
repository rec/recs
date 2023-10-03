import dataclasses as dc
import sys
import traceback
import typing as t
from functools import cached_property

from sounddevice import InputStream, query_devices

from recs import Array, DType

StopCallback = t.Callable[[], None]
DeviceCallback = t.Callable[[Array], None]


@dc.dataclass(frozen=True)
class InputDevice:
    info: dict[str, t.Any]
    dtype: t.Any = DType

    def __bool__(self):
        return bool(self.channels)

    @cached_property
    def channels(self):
        return self.info['max_input_channels']

    @cached_property
    def samplerate(self) -> int:
        return int(self.info['default_samplerate'])

    @cached_property
    def name(self):
        return self.info['name']

    def input_stream(self, callback: DeviceCallback, stop: StopCallback) -> InputStream:
        def _callback(indata: Array, frames, time, status):
            try:
                if status:
                    print('Status', self.name, status, file=sys.stderr)
                callback(indata.copy())
            except Exception:
                traceback.print_exc()
                stop()

        return InputStream(
            callback=_callback,
            channels=self.channels,
            device=self.name,
            dtype=self.dtype,
            samplerate=self.samplerate,
        )


def input_devices() -> dict[str, InputDevice]:
    return {d.name: d for i in query_devices() if (d := InputDevice(i))}


@dc.dataclass
class InputDevices:
    devices: dict[str, InputDevice] = dc.field(default_factory=input_devices)

    def __getitem__(self, key: str) -> InputDevice:
        try:
            return self.devices[key]
        except KeyError:
            key = key.lower()
            try:
                return self.devices[key]
            except KeyError:
                pass

            items = self.devices.items()
            if 1 == len(m := [v for k, v in items if k.lower().startswith(key)]):
                return m[0]
            raise
