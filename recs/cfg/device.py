import json
import subprocess as sp
import sys
import traceback
import typing as t

import numpy as np

from recs.base import times
from recs.base.prefix_dict import PrefixDict
from recs.base.types import DeviceDict, SdType, Stop
from recs.cfg import hash_cmp

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

    @property
    def is_online(self) -> bool:
        # TODO: this is wrong!
        # https://github.com/spatialaudio/python-sounddevice/issues/382
        # return any(self.name == i['name'] for i in sd.query_devices())
        return True

    def input_stream(
        self, callback: Callback, dtype: SdType, stop_all: Stop
    ) -> t.Iterator[None] | None:
        import sounddevice as sd

        if not self.is_online:
            return None

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

            except Exception as e:  # pragma: no cover
                # TODO: move this to the audio device_queue
                if False:
                    traceback.print_exc()
                else:
                    print(e)
                try:
                    stop_all()
                except Exception:
                    traceback.print_exc()

        stream = sd.InputStream(
            callback=cb,
            channels=self.channels,
            device=self.name,
            dtype=str(dtype),
            samplerate=self.samplerate,
        )
        stream._recs_timestamp = times.time()
        return stream


InputDevices = PrefixDict[InputDevice]


def get_input_devices(devices: t.Sequence[DeviceDict]) -> InputDevices:
    return PrefixDict({d.name: d for i in devices if (d := InputDevice(i))})


P = 'import json, sounddevice; print(json.dumps(sounddevice.query_devices(), indent=4))'


def query_devices() -> t.Sequence[DeviceDict]:
    r = sp.run(('python', '-c', P), text=True, check=True, stdout=sp.PIPE)
    return json.loads(r.stdout)


def input_devices() -> InputDevices:
    return get_input_devices(query_devices())
