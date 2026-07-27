import numpy as np

from recs.cfg import Cfg
from recs.cfg.source import Update
from recs.ui.source_recorder import InputBuffer


def test_input_buffer_drops_updates_when_full() -> None:
    buffer = InputBuffer(Cfg(audio_buffer_seconds=0.001), samplerate=48_000)
    update = Update(np.zeros((512, 1)), 10.0)

    buffer.put(update)
    buffer.put(update)

    assert buffer.get(block=False).update is update
    assert buffer.stats.dropped_blocks == 1
    assert buffer.stats.dropped_frames == 512
    assert buffer.stats.last_drop_timestamp == 10.0


def test_input_buffer_timeline_includes_dropped_updates() -> None:
    buffer = InputBuffer(Cfg(audio_buffer_seconds=0.001), samplerate=48_000)
    first = Update(np.zeros((512, 1)), 10.0)
    dropped = Update(np.zeros((256, 1)), 11.0)
    third = Update(np.zeros((128, 1)), 12.0)

    buffer.put(first)
    buffer.put(dropped)
    assert buffer.get(block=False).end_frame == 512
    buffer.put(third)

    result = buffer.get(block=False)
    assert result.start_frame == 768
    assert result.end_frame == 896


def test_input_buffer_reports_overflow_and_pressure_once() -> None:
    cfg = Cfg(
        audio_buffer_seconds=0.001,
        buffer_status_period=1,
        buffer_warning_fraction=1,
    )
    buffer = InputBuffer(cfg, samplerate=48_000)
    update = Update(np.zeros((512, 1)), 10.0)

    buffer.put(update)
    buffer.put(update)
    warnings = buffer.warnings('Mic', 10.0)

    assert warnings == [
        'Device Mic audio buffer overflow: dropped 512 frames',
        'Device Mic audio buffer pressure: 0.011 seconds queued',
    ]
    assert buffer.warnings('Mic', 10.5) == []
