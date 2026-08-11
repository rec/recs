import threading
import time

import numpy as np

from recs.base.state import ChannelState
from recs.cfg.cfg import Cfg
from recs.cfg.source import Update
from recs.ui.source_recorder import InputBuffer, SourceUpdate, SourceUpdateTransport


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


def test_source_updates_do_not_block_when_parent_read_blocks() -> None:
    connection = BlockingConnection()
    transport = SourceUpdateTransport(connection)
    first = SourceUpdate(
        channels={'1': ChannelState()},
        files=[],
        frames=512,
        source_name='Mic',
    )
    second = first._replace(frames=256)
    transport.start()
    transport.publish(first)
    assert connection.started.wait(0.1)

    start = time.monotonic()
    transport.publish(second)

    assert time.monotonic() - start < 0.1
    connection.release.set()
    assert connection.finished.wait(0.1)
    transport.stop()


class BlockingConnection:
    def __init__(self) -> None:
        self.started = threading.Event()
        self.release = threading.Event()
        self.finished = threading.Event()

    def send(self, message: object) -> None:
        self.started.set()
        self.release.wait()
        self.finished.set()
