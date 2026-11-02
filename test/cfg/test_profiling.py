import sys
from pathlib import Path

import numpy as np
import pytest
import soundfile

from recs.base.errors import RecsError
from recs.base.types import SdType
from recs.cfg import profile_devices, profiling
from recs.cfg.cfg import Cfg


@pytest.mark.parametrize(
    'spec', ['', '0', '-1', '18:0', '18:', ':10', '1.5', 'a', '１']
)
def test_invalid_fake_device_specs_are_rejected(spec: str) -> None:
    with pytest.raises(ValueError, match='positive integers'):
        Cfg(profile_fake=spec)


def test_fake_inventory_matches_requested_devices(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(profile_devices.FAKE_DEVICES_ENV, '18:10')
    devices = profile_devices.inventory()
    assert devices is not None
    assert [d['max_input_channels'] for d in devices] == [18, 10]
    assert all(d['default_samplerate'] == 48_000 for d in devices)


def test_profile_requires_python_315(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(profiling.ACTIVE_ENV, raising=False)
    monkeypatch.setattr(sys, 'version_info', (3, 13))
    with pytest.raises(RecsError, match='Python 3.15'):
        profiling.launch(Cfg(profile=True))


def test_profile_launch_preserves_arguments_and_follows_workers(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv(profiling.ACTIVE_ENV, raising=False)
    monkeypatch.setattr(sys, 'version_info', (3, 15))
    monkeypatch.setattr(profiling, 'find_spec', lambda name: object())
    monkeypatch.setattr(sys, 'argv', ['recs', '--profile-fake=18:10', '-t', '2'])
    calls = []
    monkeypatch.setattr(profiling.os, 'execve', lambda *args: calls.append(args))
    profiling.launch(Cfg(profile_fake='18:10'))
    executable, command, environment = calls[0]
    assert executable == sys.executable
    assert '--subprocesses' in command and '--all-threads' in command
    assert command[-4:] == ['recs', '--profile-fake=18:10', '-t', '2']
    assert environment[profile_devices.FAKE_DEVICES_ENV] == '18:10'
    assert environment[profiling.ACTIVE_ENV] == '1'
    calls.clear()
    monkeypatch.setenv(profiling.ACTIVE_ENV, '1')
    profiling.launch(Cfg(profile=True))
    assert not calls


@pytest.mark.parametrize('dtype', [SdType.float32, SdType.int16, SdType.int32])
def test_fake_capture_produces_owned_audio_and_stops(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    dtype: SdType,
) -> None:
    updates = []
    stream = profile_devices.FakeInputStream(2, dtype, updates.append)

    # Advance virtual pacing to exercise one second of capture without waiting.
    def wait(seconds: float) -> bool:
        if len(updates) >= 50:
            stream.stop()
        return stream.cancelled.is_set()

    monkeypatch.setattr(stream.cancelled, 'wait', wait)
    stream.capture()
    assert len(updates) == 50
    samples = np.concatenate([u.array for u in updates])
    assert samples.shape == (48_000, 2)
    assert samples.dtype == np.dtype(dtype)
    assert np.any(samples)
    assert updates[-1].timestamp - updates[0].timestamp == pytest.approx(0.98)
    soundfile.write(tmp_path / 'fake.wav', samples, 48_000)


def test_cli_accepts_equals_device_spec() -> None:
    import tyro

    from recs.cfg.cli import CliCfg

    cfg = tyro.cli(CliCfg, args=['--profile-fake=18:10'])
    assert cfg.general.profile_fake == '18:10'


def test_fake_device_opens_synthetic_stream_without_portaudio(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import sounddevice

    from recs.cfg.device import InputDevice

    monkeypatch.setenv(profile_devices.FAKE_DEVICES_ENV, '18:10')
    monkeypatch.setattr(
        sounddevice, 'InputStream', lambda **kwargs: pytest.fail('PortAudio opened')
    )
    devices = profile_devices.inventory()
    assert devices is not None
    stream = InputDevice(devices[1]).input_stream(SdType.float32, lambda update: None)
    assert isinstance(stream, profile_devices.FakeInputStream)
    assert stream.channels == 10
