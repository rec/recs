from . import DType
import dataclasses as dc
import sounddevice as sd
import sys
import typing as t


@dc.dataclass(frozen=True)
class InputDevice:
    info: t.Dict[str, t.Any]
    dtype: t.Any = DType
    block_count = 0

    def __bool__(self):
        return bool(self.channels)

    def channels(self):
        return self.info['max_input_channels']

    def samplerate(self) -> int:
        return int(self.info['default_samplerate'])

    def name(self):
        return self.info['name']

    def input_stream(self, callback):
        def _callback(indata, frames, time, status):
            self.block_count += 1
            if status:
                print(status, file=sys.stderr)
            callback(indata.copy(), self)

        return sd.InputStream(
            callback=_callback,
            channels=self.channels,
            device=self.name,
            dtype=self.dtype,
            samplerate=self.samplerate,
        )


def input_devices():
    return {d.name: d for i in sd.query_devices() if (d := InputDevice(i))}
