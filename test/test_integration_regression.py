import copy
import traceback
import typing as t
from pathlib import Path

import numpy as np
import pytest
import soundfile
import tdir
from pytest_regressions.file_regression import FileRegressionFixture
from threa import HasThread

from recs.base import times
from recs.cfg import Cfg, device, run_cli

from .conftest import TIMESTAMP, wait

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


class DummyConnectionModule:
    Connection = object

    @staticmethod
    def wait(
        connections: t.Sequence[object], timeout: float | None = None
    ) -> list[object]:
        return wait(connections, timeout)


class FixtureInputStream:
    def __init__(
        self,
        callback: t.Callable[[np.ndarray, int, object, int], None],
        channels: int,
        device: str,
        dtype: object,
        samplerate: int,
    ) -> None:
        self.callback = callback
        self.channels = channels
        self.device = device
        self.dtype = np.dtype(str(dtype))
        self.samplerate = samplerate
        self.position = 0
        self.running = False
        self.report: list[str] = []
        self.audio = _audio(device).astype(self.dtype)
        assert self.audio.shape[1] == channels

    def start(self) -> None:
        self.running = True
        self.report.append('start')

    def stop(self, ignore_errors: bool = True) -> None:
        self.running = False
        self.report.append('stop')

    def close(self, ignore_errors: bool = True) -> None:
        self.stop(ignore_errors=ignore_errors)
        self.report.append('close')

    def send_next(self) -> None:
        if not self.running:
            return

        end = self.position + BLOCK_SIZE
        array = self.audio[self.position : end]
        self.position = end
        self.callback(array, len(array), None, 0)


class RegressionRunner:
    def __init__(
        self, monkeypatch: pytest.MonkeyPatch, output_directory: Path
    ) -> None:
        import sounddevice

        monkeypatch.setattr(device, 'query_devices', self.query_devices)
        monkeypatch.setitem(
            run_cli.Recorder._run.__globals__,
            'connection',
            DummyConnectionModule,
        )
        monkeypatch.setattr(sounddevice, 'InputStream', self.input_stream)
        monkeypatch.setattr(times, 'timestamp', self.timestamp)

        self._timestamp = TIMESTAMP
        self.error = ''
        self.output_directory = output_directory
        self.streams: list[FixtureInputStream] = []

    def query_devices(self) -> list[device.DeviceDict]:
        return copy.deepcopy(DEVICES)

    def input_stream(self, **kwargs: object) -> FixtureInputStream:
        stream = FixtureInputStream(
            callback=t.cast(
                t.Callable[[np.ndarray, int, object, int], None],
                kwargs['callback'],
            ),
            channels=t.cast(int, kwargs['channels']),
            device=t.cast(str, kwargs['device']),
            dtype=kwargs['dtype'],
            samplerate=t.cast(int, kwargs['samplerate']),
        )
        self.streams.append(stream)
        return stream

    def timestamp(self) -> float:
        return self._timestamp

    def run(self) -> list[Path]:
        self.error = ''
        cfg = Cfg(
            band_mode=False,
            clear=False,
            output_directory=str(self.output_directory),
            quiet_after_end=0,
            quiet_before_start=0,
            shortest_file_time=0,
            silent=True,
            stop_after_quiet=1,
            total_run_time=RUN_TIME,
        )

        thread = HasThread(lambda: self._run_cli(cfg), name='RunCli')
        thread.start()
        try:
            self._wait_for_streams()
            for block in range(BLOCKS):
                self._timestamp = TIMESTAMP + block * BLOCK_SIZE / SAMPLERATE
                for stream in self.streams:
                    stream.send_next()
            self._wait_for_stop()
        finally:
            thread.stop()
            thread.join(timeout=1)

        if thread.running:
            raise AssertionError('run_cli thread did not stop')

        if self.error:
            raise AssertionError(self.error)

        return sorted(self.output_directory.glob('*.wav'))

    def _run_cli(self, cfg: Cfg) -> None:
        try:
            run_cli.Recorder._run.__globals__['connection'] = DummyConnectionModule
            assert (
                run_cli.Recorder._run.__globals__['connection']
                is DummyConnectionModule
            )
            run_cli.run_cli(cfg)
        except ValueError as e:
            if 'Invalid file object' in str(e):
                return
            self.error = traceback.format_exc()
        except Exception:
            self.error = traceback.format_exc()

    def _wait_for_streams(self) -> None:
        for _ in range(1_000):
            if self.error:
                raise AssertionError(self.error)
            if len(self.streams) == 2 and all(
                stream.running for stream in self.streams
            ):
                return
            times.sleep(0.001)
        raise AssertionError(f'Streams did not start: {self.streams}')

    def _wait_for_stop(self) -> None:
        for _ in range(1_000):
            if self.error:
                raise AssertionError(self.error)
            if all('stop' in stream.report for stream in self.streams):
                return
            times.sleep(0.001)
        raise AssertionError(f'Streams did not stop: {self.streams}')


@tdir
def test_hardware_recording_regression(
    file_regression: FileRegressionFixture,
    mock_mp: None,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    first = RegressionRunner(monkeypatch, tmp_path / 'first').run()
    second = RegressionRunner(monkeypatch, tmp_path / 'second').run()

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
