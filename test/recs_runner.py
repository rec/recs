import traceback
import typing as t
from pathlib import Path
from test.conftest import BLOCK_SIZE, TIMESTAMP
from test.mock_input_stream import InputStreamReporter

import numpy as np
import soundfile
from threa import HasThread

from recs.base import times
from recs.base.types import Format
from recs.cfg import Cfg, run_cli

DEVICE_OFFSET = 0.000_0237
TRIES = 100
DELAY = 0.001


class FixtureInputStream:
    def __init__(
        self,
        callback: t.Callable[[np.ndarray, int, object, int], None],
        channels: int,
        device: str,
        dtype: object,
        samplerate: int,
        audio: np.ndarray,
        block_size: int,
    ) -> None:
        self.callback = callback
        self.channels = channels
        self.device = device
        self.dtype = np.dtype(str(dtype))
        self.samplerate = samplerate
        self._recs_audio = audio.astype(self.dtype)
        self._recs_block_size = block_size
        self._recs_position = 0
        self._recs_report: list[str] = []
        assert self._recs_audio.shape[1] == channels

    def start(self) -> None:
        self._recs_report.append('start')

    def stop(self, ignore_errors: bool = True) -> None:
        self._recs_report.append('stop')

    def close(self, ignore_errors: bool = True) -> None:
        self._recs_report.append('close')

    def _recs_callback(self) -> None:
        end = self._recs_position + self._recs_block_size
        array = self._recs_audio[self._recs_position : end]
        self._recs_position = end
        self.callback(array, len(array), None, 0)


class RecsRunner:
    _timestamp = TIMESTAMP

    def __init__(
        self,
        cfg: dict[str, object],
        monkeypatch: t.Any,
        event_count: int | None = None,
        input_audio: dict[str, np.ndarray] | None = None,
        block_size: int = BLOCK_SIZE,
        device_offset: float = DEVICE_OFFSET,
        event_multiplier: int = 2,
        expected_streams: int | None = None,
        total_run_time: float = 0.1,
        wait_for_stop: bool = False,
    ) -> None:
        import sounddevice

        monkeypatch.setattr(sounddevice, 'InputStream', self.make_input_stream)
        monkeypatch.setattr(times, 'timestamp', self.timestamp)

        self.block_size = block_size
        self.device_offset = device_offset
        self.event_count = event_count
        self.event_multiplier = event_multiplier
        self.expected_streams = expected_streams
        self.input_audio = input_audio or {}
        self._timestamp = TIMESTAMP
        self.wait_for_stop = wait_for_stop
        self.streams: list[InputStreamReporter | FixtureInputStream] = []
        self.cfg = Cfg(shortest_file_time=0, total_run_time=total_run_time, **cfg)

    def make_input_stream(
        self, **ka: object
    ) -> InputStreamReporter | FixtureInputStream:
        device = t.cast(str, ka['device'])
        audio = self.input_audio.get(device)
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
                block_size=self.block_size,
            )
        else:
            s = InputStreamReporter(**ka)
        self.streams.append(s)
        return s

    def events(
        self,
    ) -> t.Iterator[tuple[float, InputStreamReporter | FixtureInputStream]]:
        for stream in self.streams:
            offset = stream.channels * self.device_offset
            block_time = self.block_size / stream.samplerate
            blocks = int(self.event_multiplier * self.cfg.total_run_time / block_time)
            for i in range(blocks):
                yield (offset + i * block_time), stream

    def timestamp(self) -> float:
        return self._timestamp

    def run_cli(self) -> None:
        try:
            run_cli.run_cli(self.cfg)
        except ValueError as e:
            if 'Invalid file object' not in str(e):
                self._error = traceback.format_exc()
        except Exception:
            self._error = traceback.format_exc()

    def run(self) -> None:
        self._error = ''
        if self.wait_for_stop:
            self._run_bounded()
            return

        with HasThread(self.run_cli, name='RunCli'):
            for _ in range(TRIES):
                if self._error:
                    raise ValueError(self._error)
                if self._ready():
                    break
                times.sleep(DELAY)
            else:
                event_count = sum(1 for _ in self.events())
                raise ValueError(f'{event_count=} {self._error=}')

            for offset, stream in sorted(self.events(), key=lambda event: event[0]):
                if 'stop' not in stream._recs_report:
                    self._timestamp = TIMESTAMP + offset
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
        if self._error:
            raise AssertionError(self._error)

    def paths(self, root: Path | None = None) -> list[Path]:
        return sorted((root or Path()).glob(f'**/*.{Format._default}'))

    def assert_matches(self, tdata: Path) -> None:
        actual = self.paths()
        expected = sorted(tdata.glob(f'**/*.{Format._default}'))

        if not expected:
            for a in actual:
                f = tdata / a
                f.parent.mkdir(exist_ok=True, parents=True)
                f.write_bytes(a.read_bytes())
            return

        assert actual == [p.relative_to(tdata) for p in expected]
        assert [p.name for p in actual] == [p.name for p in expected]

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

    def _ready(self) -> bool:
        if (
            self.expected_streams is not None
            and len(self.streams) < self.expected_streams
        ):
            return False
        event_count = sum(1 for _ in self.events())
        if self.event_count is not None:
            return event_count >= self.event_count
        return bool(event_count)

    def _send_events(self) -> None:
        for offset, stream in sorted(self.events(), key=lambda event: event[0]):
            if 'stop' not in stream._recs_report:
                self._timestamp = TIMESTAMP + offset
                stream._recs_callback()

    def _wait_until_ready(self) -> None:
        for _ in range(TRIES):
            if self._error:
                raise AssertionError(self._error)
            if self._ready():
                return
            times.sleep(DELAY)
        event_count = sum(1 for _ in self.events())
        raise AssertionError(f'{event_count=} {self._error=}')

    def _wait_until_stopped(self) -> None:
        for _ in range(TRIES):
            if self._error:
                raise AssertionError(self._error)
            if all('stop' in stream._recs_report for stream in self.streams):
                return
            times.sleep(DELAY)
        raise AssertionError(f'Streams did not stop: {self.streams}')
