import traceback
import typing as t
from pathlib import Path
from test.conftest import BLOCK_SIZE, TIMESTAMP
from test.mock_input_stream import InputStreamReporter

import numpy as np
import pytest
import soundfile
from pydantic import BaseModel, ConfigDict, Field, PrivateAttr
from threa import HasThread

from recs.base import times
from recs.base.types import Format
from recs.cfg import Cfg, run_cli

DEVICE_OFFSET = 0.000_0237
TRIES = 100
DELAY = 0.001


class FixtureInputStream(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    audio: np.ndarray
    block_size: int
    callback: t.Callable[[np.ndarray, int, object, int], None]
    channels: int
    device: str
    dtype: object
    samplerate: int

    _position: int = PrivateAttr(default=0)
    _report: list[str] = PrivateAttr(default_factory=list)

    def model_post_init(self, __context: object) -> None:
        self.dtype = np.dtype(str(self.dtype))
        self.audio = self.audio.astype(self.dtype)
        assert self.audio.shape[1] == self.channels

    @property
    def _recs_report(self) -> list[str]:
        return self._report

    def start(self) -> None:
        self._report.append('start')

    def stop(self, ignore_errors: bool = True) -> None:
        self._report.append('stop')

    def close(self, ignore_errors: bool = True) -> None:
        self._report.append('close')

    def _recs_callback(self) -> None:
        end = self._position + self.block_size
        array = self.audio[self._position : end]
        self._position = end
        self.callback(array, len(array), None, 0)


class RecsRunnerOptions(BaseModel):
    block_size: int = BLOCK_SIZE
    device_offset: float = DEVICE_OFFSET
    event_count: int | None = None
    event_multiplier: int = 2
    expected_streams: int | None = None
    wait_for_stop: bool = False


class RecsRunnerState(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    input_audio: dict[str, np.ndarray] = Field(default_factory=dict)
    streams: list[InputStreamReporter | FixtureInputStream] = Field(
        default_factory=list
    )
    error: str = ''
    timestamp: float = TIMESTAMP


class RecsRunner(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    cfg: Cfg
    monkeypatch: pytest.MonkeyPatch
    options: RecsRunnerOptions
    state: RecsRunnerState

    def __init__(
        self,
        cfg: dict[str, object],
        monkeypatch: pytest.MonkeyPatch,
        event_count: int | None = None,
        input_audio: dict[str, np.ndarray] | None = None,
        block_size: int = BLOCK_SIZE,
        device_offset: float = DEVICE_OFFSET,
        event_multiplier: int = 2,
        expected_streams: int | None = None,
        total_run_time: float = 0.1,
        wait_for_stop: bool = False,
    ) -> None:
        super().__init__(
            cfg=Cfg(shortest_file_time=0, total_run_time=total_run_time, **cfg),
            monkeypatch=monkeypatch,
            options=RecsRunnerOptions(
                block_size=block_size,
                device_offset=device_offset,
                event_count=event_count,
                event_multiplier=event_multiplier,
                expected_streams=expected_streams,
                wait_for_stop=wait_for_stop,
            ),
            state=RecsRunnerState(input_audio=input_audio or {}),
        )

        import sounddevice

        monkeypatch.setattr(sounddevice, 'InputStream', self.make_input_stream)
        monkeypatch.setattr(times, 'timestamp', self.timestamp)

    def make_input_stream(
        self, **ka: object
    ) -> InputStreamReporter | FixtureInputStream:
        device = t.cast(str, ka['device'])
        audio = self.state.input_audio.get(device)
        if audio is not None:
            s = FixtureInputStream(
                callback=t.cast(
                    t.Callable[[np.ndarray, int, object, int], None],
                    ka['callback'],
                ),
                channels=t.cast(int, ka['channels']),
                device=device,
                dtype=ka['dtype'],
                samplerate=t.cast(int, ka['samplerate']),
                audio=audio,
                block_size=self.options.block_size,
            )
        else:
            s = InputStreamReporter(**ka)
        self.state.streams.append(s)
        return s

    def events(
        self,
    ) -> t.Iterator[tuple[float, InputStreamReporter | FixtureInputStream]]:
        for stream in self.state.streams:
            offset = stream.channels * self.options.device_offset
            block_time = self.options.block_size / stream.samplerate
            blocks = int(
                self.options.event_multiplier
                * self.cfg.recording.total_run_time
                / block_time
            )
            for i in range(blocks):
                yield (offset + i * block_time), stream

    def timestamp(self) -> float:
        return self.state.timestamp

    def run_cli(self) -> None:
        try:
            run_cli.run_cli(self.cfg)
        except ValueError as e:
            if 'Invalid file object' not in str(e):
                self.state.error = traceback.format_exc()
        except Exception:
            self.state.error = traceback.format_exc()

    def run(self) -> None:
        self.state.error = ''
        if self.options.wait_for_stop:
            self._run_bounded()
            return

        with HasThread(self.run_cli, name='RunCli'):
            for _ in range(TRIES):
                if self.state.error:
                    raise ValueError(self.state.error)
                if self._ready():
                    break
                times.sleep(DELAY)
            else:
                event_count = sum(1 for _ in self.events())
                raise ValueError(f'event_count={event_count} error={self.state.error}')

            for offset, stream in sorted(self.events(), key=lambda event: event[0]):
                if 'stop' not in stream._recs_report:
                    self.state.timestamp = TIMESTAMP + offset
                    stream._recs_callback()

    def _run_bounded(self) -> None:
        thread = HasThread(self.run_cli, name='RunCli')
        thread.start()
        try:
            self._wait_until_ready()
            self._send_events()
            self._wait_until_stopped()
        finally:
            thread.stop()
            thread.join(timeout=1)

        if thread.running:
            raise AssertionError('run_cli thread did not stop')
        if self.state.error:
            raise AssertionError(self.state.error)

    def paths(self, root: Path | None = None) -> list[Path]:
        return sorted((root or Path()).glob(f'**/*.{Format._default}'))

    def assert_matches(self, tdata: Path) -> None:
        actual = self.paths()
        relative_actual = self._relative_actual_paths(actual)
        expected = sorted(tdata.glob(f'**/*.{Format._default}'))

        if not expected:
            for actual_path, relative_path in zip(actual, relative_actual, strict=True):
                f = tdata / relative_path
                f.parent.mkdir(exist_ok=True, parents=True)
                f.write_bytes(actual_path.read_bytes())
            return

        assert relative_actual == [p.relative_to(tdata) for p in expected]
        assert [p.name for p in relative_actual] == [p.name for p in expected]

        actual_expected = list(zip(actual, expected, strict=False))
        named_audio = [
            (a.name, soundfile.read(a)[0], soundfile.read(e)[0])
            for a, e in actual_expected
        ]
        shapes = [
            (n, a.shape, e.shape) for n, a, e in named_audio if a.shape != e.shape
        ]
        assert shapes == []

        differs = [n for n, a, e in named_audio if not np.allclose(a, e)]
        assert differs == []

    def _relative_actual_paths(self, paths: list[Path]) -> list[Path]:
        if self.cfg.directory.output_directory or not paths:
            return paths

        parents = {path.parent for path in paths}
        assert len(parents) == 1
        parent = parents.pop()
        assert parent.name.startswith('recs: ')
        return [path.relative_to(parent) for path in paths]

    def _ready(self) -> bool:
        if (
            self.options.expected_streams is not None
            and len(self.state.streams) < self.options.expected_streams
        ):
            return False
        event_count = sum(1 for _ in self.events())
        if self.options.event_count is not None:
            return event_count >= self.options.event_count
        return bool(event_count)

    def _send_events(self) -> None:
        for offset, stream in sorted(self.events(), key=lambda event: event[0]):
            if 'stop' not in stream._recs_report:
                self.state.timestamp = TIMESTAMP + offset
                stream._recs_callback()

    def _wait_until_ready(self) -> None:
        for _ in range(TRIES):
            if self.state.error:
                raise AssertionError(self.state.error)
            if self._ready():
                return
            times.sleep(DELAY)
        event_count = sum(1 for _ in self.events())
        raise AssertionError(f'event_count={event_count} error={self.state.error}')

    def _wait_until_stopped(self) -> None:
        for _ in range(TRIES):
            if self.state.error:
                raise AssertionError(self.state.error)
            if all('stop' in stream._recs_report for stream in self.state.streams):
                return
            times.sleep(DELAY)
        raise AssertionError(f'Streams did not stop: {self.state.streams}')
