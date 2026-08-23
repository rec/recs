import json
import subprocess
from collections.abc import Callable, Sequence
from typing import Any, cast

import numpy as np
from overrides import override
from pydantic import BaseModel, ConfigDict, Field, field_validator
from threa import Runnable, Wrapper

from recs.base import app_command, times
from recs.base.prefix_dict import PrefixDict
from recs.base.types import SdType

from .source import Source, Update

DeviceDict = dict[str, float | int | str]
DEVICE_QUERY_TIMEOUT = 5.0
STABLE_DEVICE_ID_FIELDS = ('uid', 'unique_id', 'persistent_id', 'guid', 'identifier')


class DeviceSpec(BaseModel):
    name: str
    audio_device_names: list[str] = Field(default_factory=list)
    midi_input_names: list[str] = Field(default_factory=list)

    model_config = ConfigDict(frozen=True)

    @field_validator('name')
    @classmethod
    def validate_name(cls, value: str) -> str:
        if not value.strip():
            raise ValueError('must not be empty')
        return value

    @field_validator('audio_device_names', 'midi_input_names')
    @classmethod
    def validate_names(cls, values: list[str]) -> list[str]:
        if any(not value.strip() for value in values):
            raise ValueError('must not contain empty values')
        return values


class InputDevice(Source):
    def __init__(self, info: DeviceDict) -> None:
        self.info = info
        super().__init__(
            channels=cast(int, self.info['max_input_channels']),
            key=device_key(info),
            name=cast(str, self.info['name']),
            samplerate=int(self.info['default_samplerate']),
        )

    @override
    def input_stream(
        self, sdtype: SdType, update_callback: Callable[[Update], None]
    ) -> Runnable:
        import sounddevice

        stream: sounddevice.InputStream

        def callback(
            indata: np.ndarray,
            frames: int,
            time: Any,
            status: int,
        ) -> None:
            timestamp = times.timestamp() - (time.currentTime - time.inputBufferAdcTime)
            update_callback(
                Update(indata.copy(), timestamp, str(status) if status else '')
            )

        stream = sounddevice.InputStream(
            callback=callback,
            channels=self.channels,
            device=self.name,
            dtype=sdtype,
            samplerate=self.samplerate,
        )
        return Wrapper(stream)


InputDevices = PrefixDict[InputDevice]


def device_key(info: DeviceDict) -> str:
    for field in STABLE_DEVICE_ID_FIELDS:
        if value := str(info.get(field, '')).strip():
            return f'{field}:{value}'
    return cast(str, info['name'])


def get_input_devices(devices: Sequence[DeviceDict]) -> InputDevices:
    return PrefixDict({d.key: d for i in devices if (d := InputDevice(i)).channels})


def query_devices() -> Sequence[DeviceDict]:
    try:
        r = subprocess.run(
            app_command.command('query-devices'),
            text=True,
            check=True,
            start_new_session=True,
            stdout=subprocess.PIPE,
            timeout=DEVICE_QUERY_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        return []
    return cast(list[DeviceDict], json.loads(r.stdout))


def input_devices() -> InputDevices:
    return get_input_devices(query_devices())
