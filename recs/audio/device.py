import dataclasses as dc
import sys
import traceback
import typing as t
from functools import cache, cached_property

import numpy as np
import sounddevice as sd

from recs.audio.file_types import DTYPE, DType

from .prefix_dict import PrefixDict

StopCallback = t.Callable[[], None]
DeviceCallback = t.Callable[[np.ndarray], None]


@dc.dataclass(frozen=True)
class InputDevice:
    info: dict[str, t.Any]

    def __bool__(self):
        return bool(self.channels)

    def __str__(self):
        return f'InputDevice({self.name})'

    @cached_property
    def channels(self) -> int:
        return self.info['max_input_channels']

    @cached_property
    def samplerate(self) -> int:
        return int(self.info['default_samplerate'])

    @cached_property
    def name(self) -> str:
        return self.info['name']

    def input_stream(
        self, callback: DeviceCallback, stop: StopCallback, dtype: DType = DTYPE
    ) -> sd.InputStream:
        def _callback(indata: np.ndarray, frames, time, status) -> None:
            try:
                if status:
                    print('Status', self.name, status, file=sys.stderr)
                callback(indata.copy())
            except Exception:
                traceback.print_exc()
                stop()

        return sd.InputStream(
            callback=_callback,
            channels=self.channels,
            device=self.name,
            dtype=dtype,
            samplerate=self.samplerate,
        )


@cache
def input_devices() -> PrefixDict[InputDevice]:
    return PrefixDict({d.name: d for i in sd.query_devices() if (d := InputDevice(i))})
