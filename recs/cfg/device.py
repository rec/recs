import json
import subprocess as sp
import sys
import traceback
import typing as t

import numpy as np

from recs.base.prefix_dict import PrefixDict
from recs.base.types import DeviceDict, SdType, Stop
from recs.cfg import hash_cmp

Callback = t.Callable[[np.ndarray], None]


class InputStream(t.Protocol):
    def close(self, ignore_errors=True) -> None:
        pass

    def start(self) -> None:
        pass

    def stop(self, ignore_errors=True) -> None:
        pass


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
        self, callback: Callback, sdtype: SdType, stop_all: Stop
    ) -> InputStream:
        import sounddevice as sd

        stream: sd.InputStream

        def cb(indata: np.ndarray, frames: int, _time: t.Any, status: int) -> None:
            if status:  # pragma: no cover
                print('Status', self, status, file=sys.stderr)

            try:
                callback(indata.copy())

            except Exception:  # pragma: no cover
                traceback.print_exc()
                try:
                    stop_all()
                except Exception:
                    traceback.print_exc()

        stream = sd.InputStream(
            callback=cb,
            channels=self.channels,
            device=self.name,
            dtype=sdtype,
            samplerate=self.samplerate,
        )
        return stream


InputDevices = PrefixDict[InputDevice]


def get_input_devices(devices: t.Sequence[DeviceDict]) -> InputDevices:
    return PrefixDict({d.name: d for i in devices if (d := InputDevice(i))})


CMD = sys.executable, '-m', 'recs.base._query_device'


def query_devices() -> t.Sequence[DeviceDict]:
    try:
        r = sp.run(CMD, text=True, check=True, stdout=sp.PIPE)
    except sp.CalledProcessError:
        return []
    return json.loads(r.stdout)


def input_names() -> t.Sequence[str]:
    return sorted(str(i['name']) for i in query_devices())


def input_devices() -> InputDevices:
    return get_input_devices(query_devices())
