import signal
from collections.abc import Callable, Iterator
from pathlib import Path
from threading import Event

import numpy as np
import pytest
import soundfile
from pytest_regressions.data_regression import DataRegressionFixture
from threa import Runnable

from recs.cfg.cfg import Cfg
from recs.cfg.device import InputDevice
from recs.cfg.source import Update
from recs.cfg.track import Track
from recs.runtime import capture_windows
from recs.runtime.capture_windows import CaptureWindows
from recs.runtime.input_buffer import BufferedUpdate
from recs.runtime.source_recorder import SourceRecorder
from recs.runtime.source_transport import SourceUpdateTransport


class QuietControl:
    def __init__(self, interrupt: bool = False) -> None:
        self.interrupt = interrupt

    def poll(self) -> bool:
        if self.interrupt:
            self.interrupt = False
            raise KeyboardInterrupt
        return False


def make_consumer(directory: Path, cfg: Cfg) -> SourceRecorder:
    source = InputDevice(
        {'name': 'Mic', 'default_samplerate': 48_000, 'max_input_channels': 1}
    )
    source.input_stream = lambda sdtype, update_callback: Runnable()
    return SourceRecorder(
        cfg,
        QuietControl(),
        directory,
        Event(),
        [Track(source, '1')],
        SourceUpdateTransport(QuietControl()),
    )


def record_partitioned(
    directory: Path,
    sizes: list[int],
    batch_seconds: float,
    shutdown: str = '',
    total_run_time: float = 0,
    sample_type: str = 'float32',
    amplitude: float = 0.25,
) -> tuple[SourceRecorder, np.ndarray]:
    sample_rate = 48_000
    source = InputDevice(
        {'name': 'Mic', 'default_samplerate': sample_rate, 'max_input_channels': 2}
    )
    samples = np.zeros((96_001, 2), dtype=np.float32)
    samples[12_000:84_000, 0] = (
        np.sin(np.arange(72_000) * (2 * np.pi * 220 / sample_rate)) * amplitude
    )
    samples[-1, 0] = 0.5
    if sample_type != 'float32':
        samples = (samples.astype(np.float64) * np.iinfo(sample_type).max).astype(
            sample_type
        )
    stop = Event()

    def input_stream(
        sdtype: object, update_callback: Callable[[Update], None]
    ) -> Runnable:
        class PartitionedInput(Runnable):
            def start(self) -> None:
                super().start()
                cursor = 0
                index = 0
                while cursor < len(samples):
                    end = min(len(samples), cursor + sizes[index % len(sizes)])
                    # Callback wall times deliberately jump without changing samples.
                    update_callback(
                        Update(
                            samples[cursor:end],
                            1000 + cursor / sample_rate + (10 if index % 2 else -10),
                        )
                    )
                    cursor = end
                    index += 1
                if shutdown == 'stop':
                    stop.set()
                if shutdown == 'signal':
                    signal.raise_signal(signal.SIGTERM)
                self.stop()

        return PartitionedInput()

    source.input_stream = input_stream
    recorder = SourceRecorder(
        Cfg(
            formats=['wav'],
            sdtype=sample_type,
            output_directory=str(directory),
            quiet_before_start=0.1,
            quiet_after_end=0.1,
            stop_after_quiet=0.5,
            shortest_file_time=10,
            processing_batch_seconds=batch_seconds,
            total_run_time=total_run_time,
        ),
        QuietControl(interrupt=shutdown == 'interrupt'),
        directory,
        stop,
        [Track(source, '1'), Track(source, '2')],
        SourceUpdateTransport(QuietControl()),
    )
    recorder.run()
    return recorder, samples


@pytest.mark.parametrize(
    ('sizes', 'batch_seconds'),
    [
        ([1], 0.1),
        ([257, 1, 383, 959], 0.05),
        ([257, 1, 383, 959], 0.1),
        ([257, 1, 383, 959], 0.2),
        ([960], 0.1),
        ([48_000], 0.1),
    ],
)
def test_detection_and_retained_samples_are_independent_of_driver_and_batch_sizes(
    tmp_path: Path, sizes: list[int], batch_seconds: float
) -> None:
    recorder, samples = record_partitioned(tmp_path, sizes, batch_seconds)
    active, silent = recorder.channel_writers
    assert recorder.sample_count == len(samples)
    assert silent.created_files == []
    assert len(active.files_written) == 1
    path = active.files_written[0]
    actual, rate = soundfile.read(path, dtype='float32')
    assert rate == 48_000
    np.testing.assert_array_equal(actual, samples[7200:, 0])
    assert active.file_start_frames[path] == 7200
    assert active.file_end_frames[path] == len(samples)
    assert [(s.start, s.count) for s in active.file_spans[path]] == [
        (7200, len(actual))
    ]


@pytest.mark.parametrize('sample_type', ['int16', 'int32'])
def test_loud_integer_audio_is_not_misclassified_by_peak_range_overflow(
    tmp_path: Path, sample_type: str
) -> None:
    recorder, samples = record_partitioned(
        tmp_path, [257, 383, 1], 0.1, sample_type=sample_type, amplitude=0.9
    )
    active, silent = recorder.channel_writers
    assert silent.created_files == []
    assert len(active.files_written) == 1
    actual, rate = soundfile.read(active.files_written[0], dtype=sample_type)
    assert rate == 48_000
    np.testing.assert_array_equal(actual, samples[7200:, 0])


@pytest.mark.parametrize('shutdown', ['stop', 'interrupt', 'signal'])
def test_shutdown_drains_queued_audio_and_partial_window_before_closing_files(
    tmp_path: Path, shutdown: str
) -> None:
    recorder, samples = record_partitioned(tmp_path, [257, 383, 1], 0.1, shutdown)
    active, silent = recorder.channel_writers
    assert silent.created_files == []
    assert recorder.sample_count == len(samples)
    actual, rate = soundfile.read(active.files_written[0], dtype='float32')
    assert rate == 48_000
    np.testing.assert_array_equal(actual, samples[7200:, 0])


def test_signal_during_window_processing_finishes_without_duplicate_samples(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    receive = CaptureWindows.receive
    signaled = [False]

    def receive_with_signal(
        windows: CaptureWindows, update: BufferedUpdate
    ) -> Iterator[BufferedUpdate]:
        if not signaled[0]:
            signaled[0] = True
            signal.raise_signal(signal.SIGTERM)
        yield from receive(windows, update)

    monkeypatch.setattr(CaptureWindows, 'receive', receive_with_signal)
    recorder, samples = record_partitioned(tmp_path, [257, 383, 1], 0.1)
    assert recorder.sample_count == len(samples)
    actual, rate = soundfile.read(
        recorder.channel_writers[0].files_written[0], dtype='float32'
    )
    assert rate == 48_000
    np.testing.assert_array_equal(actual, samples[7200:, 0])


def test_explicit_run_limit_is_exact_even_when_more_audio_is_already_queued(
    tmp_path: Path,
) -> None:
    recorder, samples = record_partitioned(tmp_path, [48_000], 0.1, total_run_time=1.5)
    assert recorder.sample_count == 72_000
    actual, rate = soundfile.read(
        recorder.channel_writers[0].files_written[0], dtype='float32'
    )
    assert rate == 48_000
    np.testing.assert_array_equal(actual, samples[7200:72_000, 0])


def test_gaps_and_backend_status_preserve_boundaries_without_inventing_samples(
    tmp_path: Path, data_regression: DataRegressionFixture
) -> None:
    windows = CaptureWindows(48_000, 0.05, 0.1)
    samples = np.linspace(-0.25, 0.25, 96_001, dtype=np.float32).reshape(-1, 1)
    output = list(
        windows.receive(BufferedUpdate(Update(samples[:48_001], 0.0), 0, 48_001))
    )
    output.extend(
        windows.receive(
            BufferedUpdate(
                Update(samples[48_001:], 1.01, 'input overflow'), 48_481, 96_481
            )
        )
    )
    if (tail := windows.flush()) is not None:
        output.append(tail)
    actual = np.concatenate([u.update.array for u in output])
    np.testing.assert_array_equal(actual, samples)
    soundfile.write(tmp_path / 'with-gap.wav', actual, 48_000, subtype='FLOAT')
    data_regression.check(
        [
            {
                'start': u.start_frame,
                'end': u.end_frame,
                'status': u.update.status,
                'uncertain': u.uncertain,
            }
            for u in output
            if u.uncertain or u.update.status
        ]
    )


def test_partial_window_has_a_bounded_wait_and_retains_owned_samples(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    now = [0.0]
    monkeypatch.setattr(capture_windows, 'monotonic', lambda: now[0])
    windows = CaptureWindows(48_000, 1.0, 1.0)
    samples = np.linspace(-0.25, 0.25, 48_000, dtype=np.float32).reshape(-1, 1)
    first = samples[:24_000].copy()
    assert list(windows.receive(BufferedUpdate(Update(first, 0.0), 0, 24_000))) == []
    first.fill(0)
    now[0] = 0.99
    assert not windows.expired
    now[0] = 1.0
    assert windows.expired
    pending = windows.flush()
    assert pending is not None and pending.uncertain
    output = list(
        windows.receive(BufferedUpdate(Update(samples[24_000:], 0.5), 24_000, 48_000))
    )
    assert output[0].uncertain
    actual = np.concatenate([pending.update.array, output[0].update.array])
    np.testing.assert_array_equal(actual, samples)
    soundfile.write(tmp_path / 'partial.wav', actual, 48_000, subtype='FLOAT')
    assert windows.flush() is None


def test_configuration_change_flushes_pending_samples_using_the_previous_settings(
    tmp_path: Path,
) -> None:
    cfg = Cfg(
        formats=['wav'],
        subtype='float',
        output_directory=str(tmp_path),
        silence_window_seconds=2,
        processing_batch_seconds=2,
        quiet_before_start=0,
        quiet_after_end=0,
    )
    recorder = make_consumer(tmp_path, cfg)
    samples = np.tile(np.array([-0.25, 0.25], dtype=np.float32), 24_000).reshape(-1, 1)
    recorder.consume_audio([BufferedUpdate(Update(samples, 0.0), 0, 48_000)])
    assert recorder.channel_writers[0].created_files == []
    recorder.control.set_cfg(
        Cfg(
            **(
                cfg.model_dump()
                | {'recording': cfg.recording.model_dump() | {'noise_floor': 0}}
            )
        ),
        revision=7,
    )
    recorder.consume_audio([BufferedUpdate(Update(samples, 1.0), 48_000, 96_000)])
    recorder.flush_pending_audio()
    writer = recorder.channel_writers[0]
    writer.stop()
    assert recorder.pending_config_revisions == []
    assert len(writer.files_written) == 1
    actual, rate = soundfile.read(writer.files_written[0], dtype='float32')
    assert rate == 48_000
    np.testing.assert_array_equal(actual, samples[:, 0])


def test_write_failure_keeps_unprocessed_windows_for_recovery(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cfg = Cfg(
        formats=['wav'],
        subtype='float',
        output_directory=str(tmp_path),
        record_everything=True,
        flush_time=0,
        flush_overlap_time=1.05,
    )
    recorder = make_consumer(tmp_path / 'old', cfg)
    samples = (
        np.sin(np.arange(144_000) * (2 * np.pi * 220 / 48_000))
        .astype(np.float32)
        .reshape(-1, 1)
    )
    original_write = soundfile.SoundFile.write
    calls = [0]

    def write(audio: soundfile.SoundFile, data: np.ndarray) -> None:
        calls[0] += 1
        if calls[0] == 21:
            raise OSError('card disconnected')
        original_write(audio, data)

    monkeypatch.setattr(soundfile.SoundFile, 'write', write)
    recorder.consume_audio([BufferedUpdate(Update(samples, 0.0), 0, len(samples))])
    assert not recorder.writing_enabled
    recorder.control.set_session_directory(tmp_path / 'new')
    recorder.control.set_writing_enabled(True, recovery_failover=True)
    recorder.consume_audio([])
    recorder.flush_pending_audio()
    writer = recorder.channel_writers[0]
    writer.stop()
    assert recorder.writing_enabled
    assert len(writer.files_written) == 1
    actual, rate = soundfile.read(writer.files_written[0], dtype='float32')
    assert rate == 48_000
    np.testing.assert_array_equal(actual, samples[:, 0])
