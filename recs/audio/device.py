import dataclasses as dc
import sys
import traceback
import typing as t

from sounddevice import InputStream, query_devices

from recs import Array, DType

DeviceCallback = t.Callable[[Array, 'InputDevice'], None]


@dc.dataclass(frozen=True)
class InputDevice:
    info: dict[str, t.Any]
    dtype: t.Any = DType
    block_count: int = 0

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

    def input_stream(self, callback: DeviceCallback, stop: t.Callable) -> InputStream:
        def _callback(indata: Array, frames, time, status):
            try:
                self.__dict__['block_count'] += 1
                if status:
                    print(status, file=sys.stderr)
                callback(indata.copy(), self)
            except BaseException:
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
