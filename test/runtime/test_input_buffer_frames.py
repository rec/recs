from queue import Empty

import numpy as np
import pytest

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
