import threading
import time
from collections.abc import Callable
from pathlib import Path

import numpy as np
import pytest
from threa import Runnable

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
    SourceCalibration,
    SourceRecorder,
    SourceUpdate,
    SourceUpdateTransport,
)


def test_input_buffer_drops_updates_when_memory_reserve_is_reached(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(source_recorder.memory, 'available_bytes', lambda: 0)
    buffer = InputBuffer(Cfg(memory_reserve_megabytes=200), samplerate=48_000)
    update = Update(np.zeros((512, 1)), 10.0)

    buffer.put(update)

    assert buffer.stats.dropped_blocks == 1
    assert buffer.stats.dropped_frames == 512
    assert buffer.stats.last_drop_timestamp == 10.0


def test_input_buffer_queue_uses_audio_seconds_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(source_recorder.memory, 'available_bytes', lambda: 400_000_000)
    buffer = InputBuffer(
        Cfg(audio_buffer_seconds=1, memory_reserve_megabytes=200), samplerate=1_000
    )
    buffer.put(Update(np.zeros((100, 1)), 10.0))

    assert buffer.queue is not None
    assert buffer.queue.maxsize == 10


def test_input_buffer_drops_updates_when_queue_is_full(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(source_recorder.memory, 'available_bytes', lambda: 400_000_000)
    buffer = InputBuffer(
        Cfg(audio_buffer_seconds=0.1, memory_reserve_megabytes=200), samplerate=1_000
    )
    buffer.put(Update(np.zeros((100, 1)), 10.0))
    buffer.put(Update(np.zeros((100, 1)), 11.0))

    assert buffer.stats.dropped_blocks == 1
    assert buffer.stats.dropped_frames == 100
    assert buffer.stats.last_drop_timestamp == 11.0


def test_input_buffer_waits_for_its_first_callback() -> None:
    buffer = InputBuffer(Cfg(), samplerate=48_000)
    received: list[object] = []
    thread = threading.Thread(
        target=lambda: received.append(buffer.get(timeout=0.1).update)
    )
    thread.start()

    update = Update(np.zeros((512, 1)), 10.0)
    buffer.put(update)
    thread.join()

    assert received == [update]


def test_input_buffer_timeline_includes_dropped_updates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    values = iter([400_000_000, 0, 400_000_000])
    timestamps = iter([1.0, 2.0, 3.0])
    monkeypatch.setattr(source_recorder.memory, 'available_bytes', lambda: next(values))
    monkeypatch.setattr(source_recorder, 'monotonic', lambda: next(timestamps))
    buffer = InputBuffer(
        Cfg(memory_check_period=1, memory_reserve_megabytes=200), samplerate=48_000
    )
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


def test_input_buffer_reports_dropped_frames_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(source_recorder.memory, 'available_bytes', lambda: 0)
    cfg = Cfg(memory_reserve_megabytes=200)
    buffer = InputBuffer(cfg, samplerate=48_000)
    update = Update(np.zeros((512, 1)), 10.0)

    buffer.put(update)
    warnings = buffer.warnings('Mic', 10.0)

    assert warnings == ['Device Mic: Dropped 512 frames in processing']
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


def test_source_update_finish_waits_for_final_send() -> None:
    connection = BlockingConnection()
    transport = SourceUpdateTransport(connection)
    transport.start()
    transport.publish(
        SourceUpdate(
            channels={'1': ChannelState()},
            files=[],
            frames=512,
            source_name='Mic',
        )
    )
    assert connection.started.wait(0.1)
    finished = threading.Event()
    thread = threading.Thread(target=lambda: (transport.finish(), finished.set()))
    thread.start()

    assert not finished.wait(0.01)
    connection.release.set()
    thread.join(0.1)

    assert finished.is_set()


def test_source_update_transport_reports_blocked_send_time() -> None:
    connection = BlockingConnection()
    transport = SourceUpdateTransport(connection)
    update = SourceUpdate(
        channels={'1': ChannelState()},
        files=[],
        frames=512,
        source_name='Mic',
        buffer_stats=source_recorder.BufferStats(),
    )
    transport.start()

    transport.publish(update)
    assert connection.started.wait(0.1)
    time.sleep(0.01)
    transport.publish(update)
    connection.release.set()
    assert connection.finished.wait(0.1)
    assert _eventually(lambda: len(connection.messages) == 2)

    second = connection.messages[1]
    assert isinstance(second, SourceUpdate)
    assert second.buffer_stats is not None
    assert second.buffer_stats.source_update_age_seconds > 0
    assert second.buffer_stats.max_source_update_send_seconds > 0
    transport.stop()


def test_source_recorder_applies_control_updates_without_audio(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = InputDevice(
        {
            'default_samplerate': 48_000,
            'max_input_channels': 1,
            'name': 'Mic',
        }
    )
    stop_event = threading.Event()
    cfg = Cfg(record_everything=True)
    connection = OneMessageControlConnection(
        source_recorder.SourceControl(cfg=cfg, cfg_revision=1),
        stop_event,
    )
    source.input_stream = lambda sdtype, update_callback: IdleInputStream()
    monkeypatch.setattr(source_recorder, 'InputBuffer', IdleInputBuffer)

    recorder = SourceRecorder(
        Cfg(),
        connection,
        stop_event,
        [Track(source, '1')],
        SourceUpdateTransport(BlockingConnection()),
    )

    assert recorder.cfg.recording.record_everything is True
    assert recorder.buffer.cfg.recording.record_everything is True
    assert recorder.pending_config_revisions == [1]


def test_source_update_merge_summarizes_warning_backlog() -> None:
    first = SourceUpdate(
        channels={'1': ChannelState()},
        files=[],
        frames=1,
        source_name='Mic',
        buffer_warnings=[f'warning {i}' for i in range(40)],
    )
    second = first._replace(
        frames=2, buffer_warnings=[f'warning {i}' for i in range(40, 80)]
    )

    result = source_recorder._merge_updates(first, second)

    assert result.buffer_warnings is not None
    assert len(result.buffer_warnings) == source_recorder.MAX_MERGED_WARNINGS
    assert result.buffer_warnings[0] == (
        'Dropped 17 older source warnings while parent was busy'
    )
    assert result.buffer_warnings[1] == 'warning 17'
    assert result.buffer_warnings[-1] == 'warning 79'


def test_source_update_merge_bounds_file_metadata_backlog() -> None:
    files = [Path(f'{i}.wav') for i in range(source_recorder.MAX_MERGED_FILES + 2)]
    first_files = files[:400]
    second_files = files[400:]
    first = SourceUpdate(
        channels={'1': ChannelState()},
        files=first_files,
        frames=1,
        source_name='Mic',
        file_records=[
            source_recorder.SourceFile(
                path=p,
                source_name='Mic',
                track=1,
                channels=1,
                sample_rate=48_000,
                bit_depth=32,
            )
            for p in first_files
        ],
        file_end_frames=dict.fromkeys(first_files, 1),
    )
    second = first._replace(
        files=second_files,
        frames=2,
        file_records=[
            source_recorder.SourceFile(
                path=p,
                source_name='Mic',
                track=1,
                channels=1,
                sample_rate=48_000,
                bit_depth=32,
            )
            for p in second_files
        ],
        file_end_frames=dict.fromkeys(second_files, 2),
    )

    result = source_recorder._merge_updates(first, second)

    assert len(result.files) == source_recorder.MAX_MERGED_FILES
    assert result.files[0] == files[2]
    assert result.files[-1] == files[-1]
    assert result.file_records is not None
    assert len(result.file_records) == source_recorder.MAX_MERGED_FILES
    assert result.file_end_frames is not None
    assert len(result.file_end_frames) == source_recorder.MAX_MERGED_FILES


def test_source_calibration_measures_exactly_half_a_second() -> None:
    source = InputDevice(
        {
            'default_samplerate': 1_000,
            'max_input_channels': 1,
            'name': 'Mic',
        }
    )
    track = Track(source, '1')
    calibration = SourceCalibration(source.samplerate)
    calibration.start(['1'])
    writer = CalibrationWriter(track)
    quiet = np.tile(np.array([-0.1, 0.1]), (400, 1))
    measured = np.tile(np.array([-0.2, 0.2]), (100, 1))
    ignored = np.tile(np.array([-0.9, 0.9]), (300, 1))

    assert calibration.update({writer: Block(block=quiet)}) is None
    result = calibration.update(
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
    recorder.file_events = source_recorder.SourceFileEvents(recorder.channel_writers)
    recorder.pending_active_channels = set()
    recorder.pending_track_layout = None
    recorder.calibration = SourceCalibration(source.samplerate)
    monkeypatch.setattr(source_recorder, 'ChannelWriter', ReconfiguredWriter)
    control = source_recorder.SourceControlApplier(recorder, EmptyControlConnection())

    control.set_tracks([Track(source, '1'), Track(source, '2')], {'Mic': {'VL': 1}})

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
        self.messages: list[object] = []

    def send(self, message: object) -> None:
        self.started.set()
        self.release.wait()
        self.messages.append(message)
        self.finished.set()


class EmptyControlConnection:
    def poll(self) -> bool:
        return False


class OneMessageControlConnection:
    def __init__(self, message: object, stop_event: threading.Event) -> None:
        self.message: object | None = message
        self.stop_event = stop_event

    def poll(self) -> bool:
        return self.message is not None

    def recv(self) -> object:
        message = self.message
        self.message = None
        self.stop_event.set()
        return message


class IdleInputBuffer:
    def __init__(self, cfg: Cfg, samplerate: float) -> None:
        self.cfg = cfg
        self.samplerate = samplerate

    def get(self, *args: object, **kwargs: object) -> object:
        raise source_recorder.Empty

    def put(self, update: object) -> None:
        pass


class IdleInputStream(Runnable):
    pass


def _eventually(check: Callable[[], bool]) -> bool:
    deadline = time.monotonic() + 1
    while time.monotonic() < deadline:
        if check():
            return True
        time.sleep(0.01)
    return False
