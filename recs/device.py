from . import Array, DType
import dataclasses as dc
import sounddevice as sd
import sys
import traceback
import typing as t

Callback = t.Callable[[Array, 'InputDevice'], t.Any]


@dc.dataclass(frozen=True)
class InputDevice:
    info: t.Dict[str, t.Any]
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

    def input_stream(self, callback: Callback, stop: t.Callable) -> sd.InputStream:
        def _callback(indata: Array, frames, time, status):
            try:
                self.__dict__['block_count'] += 1
                if status:
                    print(status, file=sys.stderr)
                callback(indata.copy(), self)
            except BaseException:
                traceback.print_exc()

                stop()

        return sd.InputStream(
            callback=_callback,
            channels=self.channels,
            device=self.name,
            dtype=self.dtype,
            samplerate=self.samplerate,
        )


def input_devices():
    return {d.name: d for i in sd.query_devices() if (d := InputDevice(i))}
