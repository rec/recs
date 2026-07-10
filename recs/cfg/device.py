import json
import subprocess as sp
import sys
import typing as t

import numpy as np
from overrides import override
from threa import Runnable, Wrapper

from recs.base import app_command, times
from recs.base.prefix_dict import PrefixDict
from recs.base.types import SdType

from .source import Source, Update

DeviceDict = dict[str, float | int | str]
DEVICE_QUERY_TIMEOUT = 5.0


class InputDevice(Source):
    def __init__(self, info: DeviceDict) -> None:
        self.info = info
        super().__init__(
            channels=t.cast(int, self.info['max_input_channels']),
            name=t.cast(str, self.info['name']),
            samplerate=int(self.info['default_samplerate']),
        )

    @override
    def input_stream(
        self, sdtype: SdType, update_callback: t.Callable[[Update], None]
    ) -> Runnable:
        import sounddevice

        stream: sounddevice.InputStream

        def callback(
            indata: np.ndarray,
            frames: int,
            time: t.Any,
            status: int,
        ) -> None:
            if status:  # pragma: no cover
                print('Status', self, status, file=sys.stderr)

            update_callback(Update(indata.copy(), times.timestamp()))

        stream = sounddevice.InputStream(
            callback=callback,
            channels=self.channels,
            device=self.name,
            dtype=sdtype,
            samplerate=self.samplerate,
        )
        return Wrapper(stream)


InputDevices = PrefixDict[InputDevice]


def get_input_devices(devices: t.Sequence[DeviceDict]) -> InputDevices:
    return PrefixDict({d.name: d for i in devices if (d := InputDevice(i)).channels})


def query_devices() -> t.Sequence[DeviceDict]:
    try:
        r = sp.run(
            app_command.command('query-devices'),
            text=True,
            check=True,
            start_new_session=True,
            stdout=sp.PIPE,
            timeout=DEVICE_QUERY_TIMEOUT,
        )
    except sp.TimeoutExpired:
        return []
    return t.cast(list[DeviceDict], json.loads(r.stdout))


def input_devices() -> InputDevices:
    return get_input_devices(query_devices())
