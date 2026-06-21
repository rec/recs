import json
import typing as t
from pathlib import Path

import numpy as np
import pytest
import soundfile
import tdir
from pytest_regressions.data_regression import DataRegressionFixture
from threa import HasThread

from recs.base import times
from recs.base.types import Format
from recs.cfg import Cfg, device, run_cli

from .conftest import BLOCK_SIZE, DEVICES, DEVICES_FILE
from .recs_runner import RecsRunner

EVENT_COUNT = 218
EVENT_COUNT_SINGLE = 75
SAMPLERATE = 48_000
BLOCK_TIME = BLOCK_SIZE / SAMPLERATE


TESTDATA = Path(__file__).parent / 'testdata/end_to_end'
FILE_INPUTS = Path(__file__).parent / 'testdata/file_inputs'
REPO_ROOT = Path(__file__).resolve().parent.parent

CASES = (
    ('default', {}, EVENT_COUNT),
    ('default', {'dry_run': True, 'silent': True}, EVENT_COUNT),
    ('single', {'include': ['flow'], 'silent': True}, EVENT_COUNT_SINGLE),
    ('time', {'output_directory': '{sdate}', 'silent': True}, EVENT_COUNT),
    (
        'device_channel',
        {'output_directory': '{device}/{channel}', 'silent': True},
        EVENT_COUNT,
    ),
)


@pytest.mark.parametrize('name, cfg, event_count', CASES)
@tdir
def test_end_to_end(name, cfg, event_count, mock_mp, mock_devices, monkeypatch):
    test_case = RecsRunner(cfg, monkeypatch, event_count)
    test_case.run()

    events = sorted(test_case.events())
    events = [(int(o * 1_000_000), s.channels) for o, s in events]
    assert len(events) == event_count

    if test_case.cfg.general.dry_run:
        assert not test_case.paths()
        return

    test_case.assert_matches(TESTDATA / name)


def test_info(mock_input_streams, capsys):
    run_cli.run_cli(Cfg(info=True))
    data = capsys.readouterr().out

    actual = json.loads(data)
    assert actual == DEVICES


@tdir
def test_file_inputs(
    data_regression: DataRegressionFixture,
    mock_mp: None,
    capsys: pytest.CaptureFixture[str],
) -> None:
    files = [FILE_INPUTS / 'mono.wav', FILE_INPUTS / 'stereo.wav']
    run_cli.run_cli(
        Cfg(
            files=files,
            output_directory='files',
            quiet_after_end=0,
            quiet_before_start=0,
            shortest_file_time=0,
            silent=True,
        )
    )

    outputs = sorted(Path('files').glob(f'*.{Format.wav}'))
    assert [path.name for path in outputs] == ['mono-1.wav', 'stereo-1.wav']

    manifest = json.loads(Path('files/recs-session.json').read_text())
    data_regression.check(
        _stable_manifest(manifest),
        basename='file_inputs_manifest',
    )

    for source, output in zip(files, outputs, strict=True):
        source_audio, source_samplerate = soundfile.read(source)
        output_audio, output_samplerate = soundfile.read(output)
        assert output_samplerate == source_samplerate
        assert np.allclose(output_audio, source_audio)

    summary = capsys.readouterr().out
    assert summary.startswith('Recording time: ')
    assert summary.endswith(
        'Files written:\n'
        '  files/mono-1.wav\n'
        '  files/stereo-1.wav\n'
    )


@tdir
def test_flaky_device_end_to_end(
    mock_mp: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    schedule = DeviceSchedule()
    monkeypatch.setattr(device, 'query_devices', schedule)
    runner = RecsRunner(
        _dynamic_cfg('flaky', ['Mic']),
        monkeypatch,
        input_audio={'Mic': _blocks(1, [1] * 8)},
        total_run_time=BLOCK_TIME * 4,
    )

    with HasThread(runner.run_cli, name='RunCli') as thread:
        schedule.set()
        schedule.set('Mic')
        first = _wait_for_stream(runner, 'Mic')
        _send_blocks(runner, [first], 2)

        schedule.set()
        _wait_until_stopped(first)

        schedule.set('Mic')
        second = _wait_for_stream(runner, 'Mic', offset=1)
        _send_blocks(runner, [second], 2)
        _wait_for_thread(thread, runner)

    assert _path_names(Path('flaky')) == [
        'flaky/Mic/1/1.wav',
        'flaky/Mic/1/1_1.wav',
    ]


@tdir
def test_long_gaps_end_to_end(
    mock_devices: None, mock_mp: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    runner = RecsRunner(
        _gap_cfg('long-gaps', ['flow + 1-2', 'flow + 3-4']),
        monkeypatch,
        expected_streams=1,
        input_audio={
            'Flower 8': _multi_track_blocks(
                10,
                {
                    0: [1, 1, 1, 0, 0, 0, 1, 1, 1],
                    1: [1, 1, 1, 0, 0, 0, 1, 1, 1],
                    2: [0, 1, 1, 1, 0, 0, 0, 1, 1],
                    3: [0, 1, 1, 1, 0, 0, 0, 1, 1],
                },
            )
        },
        event_multiplier=1,
        total_run_time=BLOCK_TIME * 9,
        wait_for_stop=True,
    )

    runner.run()

    assert _path_names(Path('long-gaps')) == [
        'long-gaps/Flower 8/1-2/1.wav',
        'long-gaps/Flower 8/1-2/2.wav',
        'long-gaps/Flower 8/3-4/1.wav',
        'long-gaps/Flower 8/3-4/2.wav',
    ]


@tdir
def test_flaky_device_and_long_gaps_end_to_end(
    mock_mp: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    schedule = DeviceSchedule()
    monkeypatch.setattr(device, 'query_devices', schedule)
    runner = RecsRunner(
        _gap_cfg('flaky-and-gaps', ['Mic', 'Ext + 1-2', 'flow + 1-2']),
        monkeypatch,
        input_audio={
            'Mic': _blocks(1, [1] * 8),
            'Ext': _multi_track_blocks(3, {0: [1, 1, 0, 0, 0, 1, 1]}),
            'Flower 8': _multi_track_blocks(10, {0: [1, 0, 0, 0, 1, 1, 1]}),
        },
        total_run_time=BLOCK_TIME * 7,
    )

    with HasThread(runner.run_cli, name='RunCli') as thread:
        schedule.set('Ext', 'Flower 8')
        ext = _wait_for_stream(runner, 'Ext')
        flower = _wait_for_stream(runner, 'Flower 8')
        _send_blocks(runner, [ext, flower], 1)

        schedule.set('Ext', 'Flower 8', 'Mic')
        mic = _wait_for_stream(runner, 'Mic')
        _send_blocks(runner, [ext, flower, mic], 2)

        schedule.set('Ext', 'Flower 8')
        _wait_until_stopped(mic)
        _send_blocks(runner, [ext, flower], 2)

        schedule.set('Ext', 'Flower 8', 'Mic')
        mic_returned = _wait_for_stream(runner, 'Mic', offset=1)
        _send_blocks(runner, [ext, flower, mic_returned], 2)
        schedule.set('Ext', 'Flower 8')
        _wait_until_stopped(mic_returned)
        _wait_for_thread(thread, runner)

    assert _path_names(Path('flaky-and-gaps')) == [
        'flaky-and-gaps/Ext/1-2/1.wav',
        'flaky-and-gaps/Ext/1-2/2.wav',
        'flaky-and-gaps/Flower 8/1-2/1.wav',
        'flaky-and-gaps/Flower 8/1-2/2.wav',
        'flaky-and-gaps/Mic/1/1.wav',
        'flaky-and-gaps/Mic/1/1_1.wav',
    ]


def _stable_manifest(manifest: dict[str, object]) -> dict[str, object]:
    result = manifest | {
        'started_at': '<timestamp>',
        'ended_at': '<timestamp>',
        'duration': '<duration>',
    }
    for file in result['files']:
        assert isinstance(file, dict)
        file['source'] = str(Path(str(file['source'])).relative_to(REPO_ROOT))
    for event in result.get('events', []):
        assert isinstance(event, dict)
        event['timestamp'] = '<timestamp>'
        source = Path(str(event['source']))
        if source.is_absolute():
            event['source'] = str(source.relative_to(REPO_ROOT))
    return result


class DeviceSchedule:
    def __init__(self) -> None:
        self.names: set[str] = set()

    def set(self, *names: str) -> None:
        self.names = set(names)

    def __call__(self) -> list[device.DeviceDict]:
        return [
            t.cast(device.DeviceDict, info.copy())
            for info in DEVICES
            if info['name'] in self.names
        ]


def _dynamic_cfg(root: str, include: list[str]) -> dict[str, object]:
    return {
        'band_mode': False,
        'clear_terminal': False,
        'devices': DEVICES_FILE,
        'include': include,
        'moving_average_time': BLOCK_TIME,
        'noise_floor': 20.0,
        'output_directory': f'{root}/{{device}}/{{channel}}/{{index}}',
        'quiet_after_end': 0,
        'quiet_before_start': 0,
        'silent': True,
        'sleep_time_device': 0.001,
        'stop_after_quiet': BLOCK_TIME * 1.5,
    }


def _gap_cfg(root: str, include: list[str]) -> dict[str, object]:
    return _dynamic_cfg(root, include) | {'sleep_time_device': 0.1}


def _blocks(channels: int, levels: list[float]) -> np.ndarray:
    wave = np.resize(np.array([1, -1], dtype=np.float32), BLOCK_SIZE)
    return np.vstack(
        [
            np.tile((wave * level / 2).reshape(-1, 1), (1, channels))
            for level in levels
        ]
    )


def _multi_track_blocks(
    channels: int, channel_levels: dict[int, list[float]]
) -> np.ndarray:
    block_count = max(len(levels) for levels in channel_levels.values())
    audio = np.zeros((block_count * BLOCK_SIZE, channels), dtype=np.float32)
    for channel, levels in channel_levels.items():
        audio[:, channel] = _blocks(1, levels).reshape(-1)
    return audio


def _send_blocks(
    runner: RecsRunner, streams: t.Sequence[object], block_count: int
) -> None:
    for _ in range(block_count):
        runner._timestamp += BLOCK_TIME
        for stream in streams:
            report = t.cast(list[str], stream._recs_report)
            if 'stop' not in report:
                stream._recs_callback()
        times.sleep(0.001)


def _wait_for_stream(
    runner: RecsRunner, device_name: str, offset: int = 0
) -> object:
    for _ in range(1000):
        matches = [stream for stream in runner.streams if stream.device == device_name]
        if len(matches) > offset:
            return matches[offset]
        times.sleep(0.001)
    raise AssertionError(f'Stream did not start: {device_name}')


def _wait_until_stopped(stream: object) -> None:
    for _ in range(1000):
        if 'stop' in stream._recs_report:
            return
        times.sleep(0.001)
    raise AssertionError(f'Stream did not stop: {stream}')


def _wait_for_thread(thread: HasThread, runner: RecsRunner) -> None:
    for _ in range(1000):
        if not thread.running:
            if runner._error:
                raise AssertionError(runner._error)
            return
        times.sleep(0.001)
    raise AssertionError('run_cli thread did not stop')


def _path_names(root: Path) -> list[str]:
    return [path.as_posix() for path in sorted(root.glob('**/*.wav'))]
