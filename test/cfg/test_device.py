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


@pytest.mark.parametrize('requested_frames', [None, 257])
def test_input_device_preserves_driver_blocks_and_uses_adc_time(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    requested_frames: int | None,
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
            **options: int,
        ) -> None:
            assert options == (
                {} if requested_frames is None else {'blocksize': requested_frames}
            )
            start = 0
            driver_sizes = iter([1, 383, 257, 959, 48_000])
            while start < len(samples):
                frames = (
                    requested_frames
                    if requested_frames is not None
                    else next(driver_sizes)
                )
                array = samples[start : start + frames].reshape(-1, channels).copy()
                callback(
                    array,
                    len(array),
                    SimpleNamespace(inputBufferAdcTime=123.25, currentTime=124.0),
                    'overflow',
                )
                array.fill(0)
                start += len(array)

    monkeypatch.setattr(sounddevice, 'InputStream', FakeInputStream)
    source = device.InputDevice(
        {'name': 'Mic', 'max_input_channels': 1, 'default_samplerate': 48_000}
    )

    source.input_stream(SdType.float32, updates.append, requested_frames)

    assert updates[0].timestamp == 199.25
    assert updates[0].status == 'overflow'
    assert [len(u.array) for u in updates[:3]] == (
        [1, 383, 257] if requested_frames is None else [257] * 3
    )
    recorded = np.concatenate([u.array for u in updates]).ravel()
    np.testing.assert_array_equal(recorded, samples)
    soundfile.write(tmp_path / 'captured.wav', recorded, 48000, subtype='FLOAT')
