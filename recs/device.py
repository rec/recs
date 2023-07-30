from . import DType

# from queue import Queue
import dataclasses as dc
import sounddevice as sd
import sys
import typing as t


@dc.dataclass(frozen=True)
class InputDevice:
    info: t.List[t.Dict]
    dtype: t.Any = DType
    block_count = 0

    def __bool__(self):
        return bool(self.channels)

    def channels(self):
        return self.info['max_input_channels']

    def name(self):
        return self.info['name']

    def input_stream(self, callback, *a, **ka):
        def _callback(indata, frames, time, status):
            self.block_count += 1
            if status:
                print(status, file=sys.stderr)
            callback(indata.copy(), *a, **ka)

        return sd.InputStream(
            callback=_callback,
            channels=self.channels,
            device=self.name,
            dtype=self.dtype,
            samplerate=int(self.info['default_samplerate']),
        )


def input_devices():
    return {d.name: d for i in sd.query_devices() if (d := InputDevice(i))}
