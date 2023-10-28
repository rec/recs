import sys
import traceback
import typing as t
from functools import cache

import numpy as np
import sounddevice as sd

from recs.audio.file_types import DTYPE
from recs.misc.prefix_dict import PrefixDict

from ..misc import hash_cmp


class InputDevice(hash_cmp.HashCmp):
    def __init__(self, info: dict[str, t.Any]) -> None:
        self.info = info
        self.channels = t.cast(int, self.info['max_input_channels'])
        self.samplerate = int(self.info['default_samplerate'])
        self.name = t.cast(str, self.info['name'])
        self._key = self.name

    def __str__(self) -> str:
        return self.name

    def input_stream(
        self, callback: t.Callable[[np.ndarray], None], stop: t.Callable[[], None]
    ) -> sd.InputStream:
        stream: sd.InputStream

        def cb(indata: np.ndarray, frames: int, time: float, status: int) -> None:
            if status:  # pragma: no cover
                # This has not yet happened, probably because we never get behind
                # the device callback cycle.
                print('Status', self, status, file=sys.stderr)

            if not indata.size:  # pragma: no cover
                print('Empty block', self, file=sys.stderr)
                return

            try:
                callback(indata.copy())  # `indata` is always the same variable!

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

        from recs.recs import RECS

        stream = sd.InputStream(
            callback=cb,
            channels=self.channels,
            device=self.name,
            dtype=RECS.dtype or DTYPE,
            samplerate=self.samplerate,
        )
        return stream


@cache
def input_devices() -> PrefixDict[InputDevice]:
    return PrefixDict({d.name: d for i in sd.query_devices() if (d := InputDevice(i))})
