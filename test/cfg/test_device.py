from collections.abc import Callable
from types import SimpleNamespace

import numpy as np
import pytest
import sounddevice

from recs.base import times
from recs.base.types import SdType
from recs.cfg import device
from recs.cfg.source import Update


def test_input_devices():
    if d := device.input_devices():
        print(next(iter(d.values())))


def test_input_devices_use_stable_host_identity() -> None:
    devices = device.get_input_devices(
        [
            {
                'default_samplerate': 48_000,
                'max_input_channels': 1,
                'name': 'USB Audio',
                'uid': 'first',
            },
            {
                'default_samplerate': 48_000,
                'max_input_channels': 2,
                'name': 'USB Audio',
                'uid': 'second',
            },
        ]
    )

    assert set(devices) == {'uid:first', 'uid:second'}
    assert [source.name for source in devices.values()] == ['USB Audio', 'USB Audio']


def test_input_device_uses_sounddevice_adc_time(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    updates: list[Update] = []
    monkeypatch.setattr(times, 'timestamp', lambda: 200.0)

    class FakeInputStream:
        def __init__(
            self,
            *,
            callback: Callable[[np.ndarray, int, object, int], None],
            channels: int,
            device: str,
            dtype: SdType,
            samplerate: int,
        ) -> None:
            array = np.zeros((512, channels), dtype=dtype)
            callback(
                array,
                len(array),
                SimpleNamespace(inputBufferAdcTime=123.25, currentTime=124.0),
                'overflow',
            )

    monkeypatch.setattr(sounddevice, 'InputStream', FakeInputStream)
    source = device.InputDevice(
        {'name': 'Mic', 'max_input_channels': 1, 'default_samplerate': 48_000}
    )

    source.input_stream(SdType.float32, updates.append)

    assert updates[0].timestamp == 199.25
    assert updates[0].status == 'overflow'
