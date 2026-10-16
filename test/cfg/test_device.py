from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
import sounddevice
import soundfile

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
    tmp_path: Path,
) -> None:
    updates: list[Update] = []
    monkeypatch.setattr(times, 'timestamp', lambda: 200.0)
    samples = np.sin(2 * np.pi * 440 * np.arange(48000) / 48000).astype(np.float32)

    class FakeInputStream:
        def __init__(
            self,
            *,
            callback: Callable[[np.ndarray, int, object, int], None],
            channels: int,
            device: str,
            dtype: SdType,
            samplerate: int,
            blocksize: int,
        ) -> None:
            for start in range(0, len(samples), blocksize):
                array = samples[start : start + blocksize].reshape(-1, channels).copy()
                callback(
                    array,
                    len(array),
                    SimpleNamespace(inputBufferAdcTime=123.25, currentTime=124.0),
                    'overflow',
                )
                array.fill(0)

    monkeypatch.setattr(sounddevice, 'InputStream', FakeInputStream)
    source = device.InputDevice(
        {'name': 'Mic', 'max_input_channels': 1, 'default_samplerate': 48_000}
    )

    source.input_stream(SdType.float32, updates.append)

    assert updates[0].timestamp == 199.25
    assert updates[0].status == 'overflow'
    assert len(updates) == 50
    recorded = np.concatenate([u.array for u in updates]).ravel()
    np.testing.assert_array_equal(recorded, samples)
    soundfile.write(tmp_path / 'captured.wav', recorded, 48000, subtype='FLOAT')
