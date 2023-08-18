import dataclasses as dc
import sys
import traceback
import typing as t

import sounddevice as sd

from . import Array, DType

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
            # print('_callback')
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


InputDevices = dict[str, InputDevice]


def input_devices() -> InputDevices:
    return {d.name: d for i in sd.query_devices() if (d := InputDevice(i))}
