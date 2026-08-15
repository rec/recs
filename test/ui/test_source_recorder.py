import threading
import time

import numpy as np
import pytest

from recs.audio.block import Block
from recs.base.state import ChannelState
from recs.base.types import Active
from recs.cfg.cfg import Cfg
from recs.cfg.device import InputDevice
from recs.cfg.source import Update
from recs.cfg.time_settings import amplitude_to_db
from recs.cfg.track import Track
from recs.ui import source_recorder
from recs.ui.source_recorder import (
    InputBuffer,
    SourceRecorder,
    SourceUpdate,
    SourceUpdateTransport,
)


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
        'Device Mic: Dropped 512 frames in processing',
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


def test_source_calibration_measures_exactly_half_a_second() -> None:
    source = InputDevice(
        {
            'default_samplerate': 1_000,
            'max_input_channels': 1,
            'name': 'Mic',
        }
    )
    track = Track(source, '1')
    recorder = object.__new__(SourceRecorder)
    recorder.source = source
    recorder._start_calibration(['1'])
    writer = CalibrationWriter(track)
    quiet = np.tile(np.array([-0.1, 0.1]), (400, 1))
    measured = np.tile(np.array([-0.2, 0.2]), (100, 1))
    ignored = np.tile(np.array([-0.9, 0.9]), (300, 1))

    assert recorder._calibration_update({writer: Block(block=quiet)}) is None
    result = recorder._calibration_update(
        {writer: Block(block=np.concatenate((measured, ignored)))}
    )

    assert result == {'1': amplitude_to_db(0.2)}


def test_source_track_change_closes_writers_before_next_buffer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = InputDevice(
        {
            'default_samplerate': 48_000,
            'max_input_channels': 2,
            'name': 'Mic',
        }
    )
    recorder = object.__new__(SourceRecorder)
    recorder.cfg = Cfg()
    recorder.times = recorder.cfg.times.scale(source.samplerate)
    recorder.input_stream = object()
    original = ReconfiguredWriter(recorder.cfg, recorder.times, Track(source, '1-2'))
    recorder.channel_writers = (original,)
    recorder.file_counts = [0]
    recorder.pending_file_end_frames = {}
    recorder.pending_file_end_timestamps = {}
    recorder.pending_active_channels = set()
    recorder.pending_track_layout = None
    monkeypatch.setattr(source_recorder, 'ChannelWriter', ReconfiguredWriter)

    recorder._set_tracks([Track(source, '1'), Track(source, '2')], {'Mic': {'VL': 1}})

    assert original.stopped
    assert [writer.track.name for writer in recorder.channel_writers] == ['1', '2']
    assert recorder.pending_active_channels == {1, 2}
    assert recorder.pending_track_layout == ['1', '2']


class ReconfiguredWriter:
    def __init__(self, cfg: Cfg, times: object, track: Track) -> None:
        self.track = track
        self.file_end_frames: dict[object, int] = {}
        self.file_end_timestamps: dict[object, float] = {}
        self.stopped = False
        self.active = Active.active

    def set_track_names(self, track_names: dict[str, dict[str, int]]) -> None:
        pass

    def stop(self) -> None:
        self.stopped = True


class CalibrationWriter:
    def __init__(self, track: Track) -> None:
        self.track = track


class BlockingConnection:
    def __init__(self) -> None:
        self.started = threading.Event()
        self.release = threading.Event()
        self.finished = threading.Event()

    def send(self, message: object) -> None:
        self.started.set()
        self.release.wait()
        self.finished.set()
