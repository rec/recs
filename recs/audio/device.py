import sys
import traceback
import typing as t
from functools import cache

import numpy as np
import sounddevice as sd

from recs.base import times
from recs.base.prefix_dict import PrefixDict
from recs.base.types import DeviceDict, SdType

from ..misc import hash_cmp

Callback = t.Callable[[np.ndarray, float], None]


class InputDevice(hash_cmp.HashCmp):
    def __init__(self, info: DeviceDict) -> None:
        self.info = info
        self.channels = t.cast(int, self.info['max_input_channels'])
        self.samplerate = int(self.info['default_samplerate'])
        self.name = t.cast(str, self.info['name'])
        self._key = self.name

    def __str__(self) -> str:
        return self.name

    def input_stream(
        self,
        callback: Callback,
        dtype: SdType,
        stop: t.Callable[[], None],
    ) -> sd.InputStream:
        stream: sd.InputStream

        def cb(indata: np.ndarray, frames: int, _time: float, status: int) -> None:
            # TODO: time is a _cffi_backend._CDataBase, not a float!

            stream._recs_timestamp = times.time()

            if status:  # pragma: no cover
                # This has not yet happened, probably because we never get behind
                # the device callback cycle.
                print('Status', self, status, file=sys.stderr)

            if not indata.size:  # pragma: no cover
                print('Empty block', self, file=sys.stderr)
                return

            try:
                # `indata` is always the same variable!
                callback(indata.copy(), stream._recs_timestamp)

            except Exception:  # pragma: no cover
                traceback.print_exc()
                try:
                    stream.stop()
                except Exception:
                    traceback.print_exc()
                try:
                    stop()
                except Exception:
                    traceback.print_exc()

        assert dtype is not None  # If sdtype is None, then the whole system blocks
        stream = sd.InputStream(
            callback=cb,
            channels=self.channels,
            device=self.name,
            dtype=dtype,
            samplerate=self.samplerate,
        )
        stream._recs_timestamp = times.time()
        return stream


def get_input_devices(devices: t.Sequence[DeviceDict]) -> PrefixDict[InputDevice]:
    return PrefixDict({d.name: d for i in devices if (d := InputDevice(i))})


@cache
def input_devices() -> PrefixDict[InputDevice]:
    return get_input_devices(sd.query_devices())
