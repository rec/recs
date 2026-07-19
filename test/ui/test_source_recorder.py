import numpy as np

from recs.cfg import Cfg
from recs.cfg.source import Update
from recs.ui.source_recorder import InputBuffer


def test_input_buffer_drops_updates_when_full() -> None:
    buffer = InputBuffer(Cfg(audio_buffer_seconds=0.001), samplerate=48_000)
    update = Update(np.zeros((512, 1)), 10.0)

    buffer.put(update)
    buffer.put(update)

    assert buffer.get(block=False) is update
    assert buffer.stats.dropped_blocks == 1
    assert buffer.stats.dropped_frames == 512
    assert buffer.stats.last_drop_timestamp == 10.0


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
