from pathlib import Path
from queue import Empty

import numpy as np
import pytest
import soundfile

from recs.base import memory
from recs.cfg.cfg import Cfg
from recs.cfg.source import Update
from recs.runtime.input_buffer import InputBuffer


@pytest.mark.parametrize('sizes', [[1, 47_999], [47_999, 1], [16_001, 16_003, 15_996]])
def test_capacity_counts_frames_independently_of_callback_sizes(
    sizes: list[int], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(memory, 'available_bytes', lambda: 400_000_000)
    buffer = InputBuffer(Cfg(audio_buffer_seconds=1), samplerate=48_000)
    cursor = 0
    for size in sizes:
        buffer.put(Update(np.zeros((size, 1), dtype=np.float32), cursor / 48_000))
        cursor += size
        assert buffer.stats.queued_seconds == cursor / 48_000
    buffer.put(Update(np.zeros((257, 1), dtype=np.float32), 1.0))
    assert buffer.stats.dropped_frames == 257
    assert buffer.stats.queued_seconds == 1
    first = buffer.get(block=False)
    assert first.start_frame == 0
    assert first.end_frame == sizes[0]
    assert buffer.stats.queued_seconds == (48_000 - sizes[0]) / 48_000
    buffer.put(Update(np.zeros((sizes[0], 1), dtype=np.float32), 2.0))
    for size in sizes[1:]:
        assert len(buffer.get(block=False).update.array) == size
    resumed = buffer.get(block=False)
    assert resumed.start_frame == 48_257
    assert resumed.end_frame == 48_257 + sizes[0]
    assert buffer.stats.queued_seconds == 0
    assert buffer.stats.max_queued_seconds == 1
    with pytest.raises(Empty):
        buffer.get(block=False)


def test_oversize_callback_does_not_overwrite_pending_audio(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(memory, 'available_bytes', lambda: 400_000_000)
    buffer = InputBuffer(Cfg(audio_buffer_seconds=1), samplerate=48_000)
    first = Update(np.ones((48_000, 1), dtype=np.float32), 0.0)
    buffer.put(first)
    buffer.put(Update(np.zeros((96_000, 1), dtype=np.float32), 1.0))
    assert buffer.stats.dropped_frames == 96_000
    assert buffer.get(block=False).update is first
    assert buffer.stats.queued_seconds == 0


def test_callback_never_reads_system_memory(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(memory, 'available_bytes', lambda: 400_000_000)
    buffer = InputBuffer(Cfg(), samplerate=48_000)
    monkeypatch.setattr(
        memory, 'available_bytes', lambda: pytest.fail('memory probe in callback')
    )
    buffer.last_memory_check = float('-inf')
    buffer.put(Update(np.zeros((48_000, 1), dtype=np.float32), 0.0))
    assert buffer.stats.queued_seconds == 1


def test_empty_buffer_read_times_out() -> None:
    buffer = InputBuffer(Cfg(), samplerate=48_000)
    with pytest.raises(Empty):
        buffer.get(timeout=0)


def test_processing_batches_preserve_samples_frames_and_status_positions(
    tmp_path: Path,
) -> None:
    buffer = InputBuffer(Cfg(), samplerate=48_000)
    samples = np.linspace(-0.25, 0.25, 48_000, dtype=np.float32).reshape(-1, 1)
    buffer.put(Update(samples, 1000.0, 'input overflow'))
    output: list[np.ndarray] = []
    cursor = 0
    while buffer.stats.queued_seconds:
        batch = buffer.get_batch(7001, block=False)
        assert sum(len(u.update.array) for u in batch) <= 7001
        for update in batch:
            assert update.start_frame == cursor
            assert update.update.timestamp == pytest.approx(1000 + cursor / 48_000)
            assert update.update.status == ('input overflow' if cursor == 0 else '')
            output.append(update.update.array)
            cursor = update.end_frame
        assert buffer.stats.queued_seconds == (len(samples) - cursor) / 48_000
    actual = np.concatenate(output)
    np.testing.assert_array_equal(actual, samples)
    soundfile.write(tmp_path / 'batched.wav', actual, 48_000, subtype='FLOAT')
