import dataclasses as dc
import sys
import traceback
import typing as t

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

    @property
    def channels(self):
        return self.info['max_input_channels']

    @property
    def samplerate(self) -> int:
        return int(self.info['default_samplerate'])

    @property
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
