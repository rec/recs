from pathlib import Path

import pytest
import soundfile

from recs.base.errors import RecsError
from recs.cfg.file_source import FileSource


def test_missing_audio_input_names_the_file(tmp_path: Path) -> None:
    path = tmp_path / 'missing.wav'

    with pytest.raises(RecsError, match='Cannot read audio input') as result:
        FileSource(path)

    assert str(path) in str(result.value)


def test_malformed_audio_input_names_the_file(tmp_path: Path) -> None:
    path = tmp_path / 'broken.wav'
    path.write_text('not an audio file')

    with pytest.raises(RecsError, match='Cannot read audio input') as result:
        FileSource(path)

    assert str(path) in str(result.value)


def test_unreadable_audio_input_reports_a_user_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / 'blocked.wav'

    def fail_open(*, file: Path, mode: str) -> soundfile.SoundFile:
        raise PermissionError('access denied')

    monkeypatch.setattr(soundfile, 'SoundFile', fail_open)

    with pytest.raises(RecsError, match='access denied') as result:
        FileSource(path)

    assert str(path) in str(result.value)


def test_file_input_waits_for_space_and_preserves_samples(tmp_path: Path) -> None:
    from queue import Empty
    from threading import Event
    from time import sleep

    import numpy as np

    from recs.cfg.cfg import Cfg
    from recs.runtime.input_buffer import InputBuffer

    path = tmp_path / 'input.wav'
    samples = np.arange(96_000, dtype=np.float32) / 96_000
    soundfile.write(path, samples, 48_000, subtype='FLOAT')
    buffer = InputBuffer(Cfg(audio_buffer_seconds=0.1), 48_000)
    stopped = Event()
    stream = FileSource(path).input_stream(
        'float32', lambda u: buffer.put(u, cancelled=stopped.is_set)
    )
    stream.start()
    result = []
    while not stream.stopped or buffer.stats.queued_blocks:
        try:
            result.append(buffer.get(timeout=0.1).update.array)
        except Empty:
            continue
        sleep(0.001)
    stream.join(1)
    assert stream.error is None
    assert buffer.stats.dropped_frames == 0
    actual = np.concatenate(result)
    np.testing.assert_array_equal(actual[:, 0], samples)
    soundfile.write(tmp_path / 'output.wav', actual, 48_000, subtype='FLOAT')


def test_file_input_stop_cancels_backpressure(tmp_path: Path) -> None:
    from time import monotonic, sleep

    import numpy as np

    from recs.cfg.cfg import Cfg
    from recs.runtime.input_buffer import InputBuffer

    path = tmp_path / 'input.wav'
    soundfile.write(path, np.zeros(48_000), 48_000)
    buffer = InputBuffer(Cfg(audio_buffer_seconds=0.1), 48_000)
    stream = FileSource(path).input_stream(
        'float32', lambda u: buffer.put(u, cancelled=lambda: not stream.running)
    )
    stream.start()
    deadline = monotonic() + 1
    while not buffer.stats.queued_blocks and monotonic() < deadline:
        sleep(0.001)
    assert buffer.stats.queued_blocks
    stream.stop()
    stream.join(1)
    assert stream.stopped
    assert buffer.stats.dropped_frames == 0


def test_file_input_reports_read_failure_after_source_was_opened(
    tmp_path: Path,
) -> None:
    import numpy as np

    path = tmp_path / 'input.wav'
    soundfile.write(path, np.zeros(48_000), 48_000)
    source = FileSource(path)
    path.write_text('file became unreadable after discovery')
    stream = source.input_stream('float32', lambda update: None)
    stream.start()
    stream.join(1)
    assert stream.stopped
    assert isinstance(stream.error, soundfile.SoundFileError)
