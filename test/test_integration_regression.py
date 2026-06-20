import copy
from pathlib import Path

import numpy as np
import pytest
import soundfile
import tdir
from pytest_regressions.file_regression import FileRegressionFixture

from recs.cfg import device

from .recs_runner import RecsRunner

SAMPLERATE = 48_000
BLOCK_SIZE = 480
RUN_TIME = 0.5
BLOCKS = round(SAMPLERATE * RUN_TIME / BLOCK_SIZE)
INPUTS = Path(__file__).parent / 'testdata/integration/inputs'

DEVICES: list[device.DeviceDict] = [
    {
        'default_samplerate': SAMPLERATE,
        'max_input_channels': 1,
        'max_output_channels': 0,
        'name': 'device-mic',
    },
    {
        'default_samplerate': SAMPLERATE,
        'max_input_channels': 0,
        'max_output_channels': 2,
        'name': 'device-out',
    },
    {
        'default_samplerate': SAMPLERATE,
        'max_input_channels': 4,
        'max_output_channels': 0,
        'name': 'device-mixer',
    },
]


@tdir
def test_hardware_recording_regression(
    file_regression: FileRegressionFixture,
    mock_mp: None,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(device, 'query_devices', query_devices)
    first = _run(monkeypatch, tmp_path / 'first')
    second = _run(monkeypatch, tmp_path / 'second')

    assert [path.name for path in first] == [
        'device-mic + 1 + 20231015-164921.wav',
        'device-mixer + 1-2 + 20231015-164921.wav',
    ]
    assert [path.name for path in second] == [path.name for path in first]
    assert [path.read_bytes() for path in second] == [
        path.read_bytes() for path in first
    ]

    for path in first:
        file_regression.check(
            path.read_bytes(),
            basename=path.stem.replace(' + ', '-'),
            binary=True,
            extension='.wav',
        )


def query_devices() -> list[device.DeviceDict]:
    return copy.deepcopy(DEVICES)


def _run(monkeypatch: pytest.MonkeyPatch, output_directory: Path) -> list[Path]:
    runner = RecsRunner(
        {
            'band_mode': False,
            'clear': False,
            'output_directory': str(output_directory),
            'quiet_after_end': 0,
            'quiet_before_start': 0,
            'silent': True,
            'stop_after_quiet': 1,
        },
        monkeypatch,
        block_size=BLOCK_SIZE,
        device_offset=0,
        event_multiplier=1,
        expected_streams=2,
        input_audio=_input_audio(),
        total_run_time=RUN_TIME,
        wait_for_stop=True,
    )
    runner.run()
    return runner.paths(output_directory)


def _input_audio() -> dict[str, np.ndarray]:
    return {
        'device-mic': _audio('device-mic'),
        'device-mixer': _audio('device-mixer'),
    }


def _audio(device_name: str) -> np.ndarray:
    mic, samplerate = soundfile.read(INPUTS / 'device-mic.wav', dtype='float32')
    assert samplerate == SAMPLERATE
    if device_name == 'device-mic':
        return mic.reshape(-1, 1)

    out_1, samplerate = soundfile.read(INPUTS / 'device-out-1.wav', dtype='float32')
    assert samplerate == SAMPLERATE
    out_2, samplerate = soundfile.read(INPUTS / 'device-out-2.wav', dtype='float32')
    assert samplerate == SAMPLERATE
    silence = np.zeros_like(out_1)
    return np.column_stack((out_1, out_2, silence, silence))
