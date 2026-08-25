import subprocess as sp
from collections.abc import Callable
from types import SimpleNamespace
from typing import Any, NoReturn

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


def test_query_device_failure_is_not_an_empty_device_list(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    error = sp.CalledProcessError(1, ['recs', 'query-devices'])

    def fail(*args: Any, **kwargs: Any) -> NoReturn:
        raise error

    monkeypatch.setattr(sp, 'run', fail)

    with pytest.raises(sp.CalledProcessError) as exc_info:
        device.query_devices()

    assert exc_info.value is error


def test_query_device_does_not_receive_terminal_interrupts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    kwargs: dict[str, Any] = {}

    def run(*args: Any, **run_kwargs: Any) -> sp.CompletedProcess[str]:
        kwargs.update(run_kwargs)
        return sp.CompletedProcess(args, 0, stdout='[]')

    monkeypatch.setattr(sp, 'run', run)

    assert device.query_devices() == []
    assert kwargs['start_new_session'] is True
    assert kwargs['timeout'] == device.DEVICE_QUERY_TIMEOUT


def test_query_device_timeout_is_empty_device_list(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def timeout(*args: Any, **kwargs: Any) -> NoReturn:
        raise sp.TimeoutExpired(['recs', 'query-devices'], timeout=5)

    monkeypatch.setattr(sp, 'run', timeout)

    assert device.query_devices() == []
