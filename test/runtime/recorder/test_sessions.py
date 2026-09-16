from datetime import datetime
from pathlib import Path

import pytest
from ufor.recording import AudioSpan
from ufor.time import Rate, Timebase

from recs.base.errors import ErrorRecord
from recs.base.state import ChannelState
from recs.cfg.cfg import Cfg
from recs.daemon import gui_protocol
from recs.recording import recording_paths, session_record
from recs.recording.capture_events import SourceFile
from recs.runtime import (
    disk_space,
    recorder,
)
from recs.runtime.recorder import Recorder
from recs.runtime.source_messages import BufferStats, SourceUpdate
from recs.ui.key_events import KeyEvent
from test.conftest import DEVICES, DEVICES_FILE
from test.runtime.recorder.fakes import (
    DiskUsage,
    FakeControlDisplay,
    FakeControlRequest,
    FakeKeyRecorder,
    FakePoller,
    FakeSourceProcess,
    read_jsonl,
    record_path,
)


def test_slow_device_clock_reports_once_per_session(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    now = 100.0
    monkeypatch.setattr(recorder.times, 'timestamp', lambda: now)
    monkeypatch.setattr(recorder, 'DevicePoller', FakePoller)
    monkeypatch.setattr(recorder, 'SourceProcess', FakeSourceProcess)
    rec = Recorder(Cfg(devices=Path(DEVICES_FILE), include=['Mic'], silent=True))
    mic_info = next(info for info in DEVICES if info['name'] == 'Mic')
    mic = rec._devices.hardware['Mic']
    rec._devices.poller.snapshots = [{'Mic': mic_info}]
    update = SourceUpdate(
        channels={'1': ChannelState()},
        files=[],
        frames=48_000,
        source_name='Mic',
    )

    rec._poll_devices()
    now = 110.0
    rec._receive_update(update)
    mic.running = True
    rec._receive_update(update)

    assert caplog.messages == ['Device Mic lagging behind real time']


def test_recorder_records_buffer_overflow_event(
    monkeypatch: pytest.MonkeyPatch,
    mock_devices: None,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(recorder.times, 'timestamp', lambda: 0.0)
    monkeypatch.setattr(recorder, 'DevicePoller', FakePoller)
    monkeypatch.setattr(recorder, 'SourceProcess', FakeSourceProcess)
    rec = Recorder(Cfg(include=['Mic'], output_directory=str(tmp_path), silent=True))
    rec._start_record()

    rec._receive_update(
        SourceUpdate(
            channels={'1': ChannelState()},
            files=[],
            frames=48_000,
            source_name='Mic',
            buffer_stats=BufferStats(
                dropped_blocks=1,
                dropped_frames=512,
                max_queued_seconds=0.5,
                queued_seconds=0.25,
            ),
        )
    )

    records = read_jsonl(record_path(rec))
    assert records[1] == {
        'type': 'buffer_overflow',
        'timestamp': '1970-01-01T00:00:00.000Z',
        'dropped_blocks': 1,
        'dropped_frames': 512,
        'source': 'Mic',
        'max_queued_seconds': 0.5,
        'queued_seconds': 0.25,
    }


def test_recorder_checks_for_unfinished_sessions_before_starting_record(
    monkeypatch: pytest.MonkeyPatch,
    mock_devices: None,
    tmp_path: Path,
) -> None:
    roots: list[Path] = []
    monkeypatch.setattr(recorder, 'SourceProcess', FakeSourceProcess)
    monkeypatch.setattr(
        recorder.recovery_report, 'report_unfinished_sessions', roots.append
    )
    rec = Recorder(Cfg(include=['Mic'], output_directory=str(tmp_path), silent=True))

    rec._start_record()

    assert roots == [tmp_path]


def test_recorder_records_buffer_pressure_before_drops(
    monkeypatch: pytest.MonkeyPatch,
    mock_devices: None,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(recorder.times, 'timestamp', lambda: 0.0)
    monkeypatch.setattr(recorder, 'DevicePoller', FakePoller)
    monkeypatch.setattr(recorder, 'SourceProcess', FakeSourceProcess)
    rec = Recorder(
        Cfg(
            audio_buffer_seconds=1,
            include=['Mic'],
            output_directory=str(tmp_path),
            silent=True,
        )
    )
    rec._start_record()

    rec._receive_update(
        SourceUpdate(
            channels={'1': ChannelState()},
            files=[],
            frames=48_000,
            source_name='Mic',
            buffer_stats=BufferStats(max_queued_seconds=0.8, queued_seconds=0.8),
        )
    )

    records = read_jsonl(record_path(rec))
    assert records[1]['type'] == 'buffer_pressure'
    assert records[1]['max_queued_seconds'] == 0.8
    assert records[1]['queued_seconds'] == 0.8


def test_recorder_output_folder_prefers_written_files(
    monkeypatch: pytest.MonkeyPatch,
    mock_devices: None,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(recorder, 'DevicePoller', FakePoller)
    monkeypatch.setattr(recorder, 'SourceProcess', FakeSourceProcess)
    rec = Recorder(Cfg(include=['Mic'], output_directory=str(tmp_path), silent=True))
    path = tmp_path / 'session/take.wav'
    path.parent.mkdir()
    path.touch()
    rec.session.files_written.add(path)

    assert rec._output_folder() == path.parent


def test_live_input_record_names_source(
    monkeypatch: pytest.MonkeyPatch,
    mock_devices: None,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(recorder, 'DevicePoller', FakePoller)
    monkeypatch.setattr(recorder, 'SourceProcess', FakeSourceProcess)
    rec = Recorder(Cfg(include=['Mic'], output_directory=str(tmp_path), silent=True))
    rec._start_record()
    path = rec.session_directory / 'audio/mic.wav'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch()

    rec._receive_update(
        SourceUpdate(
            channels={'1': ChannelState()},
            files=[path],
            frames=48_000,
            source_name='Mic',
            file_records=[
                SourceFile(
                    path=path,
                    source_name='Mic',
                    track_name='1',
                    source_channels=[1],
                    channels=1,
                    sample_rate=48_000,
                    bit_depth=64,
                )
            ],
        )
    )
    rec._finish_record()

    records = read_jsonl(record_path(rec))
    for record in records:
        record.pop('timestamp', None)
    assert records[1:3] == [
        {
            'type': 'file_started',
            'media_type': 'audio',
            'stream_id': 'audio:Mic:1',
            'clock_id': 'clock-1f0ebc6982b6c2d2',
            'source': 'Mic',
            'format': 'wav',
            'path': 'audio/mic.wav',
            'track_name': '1',
            'source_channels': [1],
            'channels': 1,
            'sample_rate': 48_000,
            'bit_depth': 64,
        },
        {
            'type': 'file_finished',
            'media_type': 'audio',
            'stream_id': 'audio:Mic:1',
            'clock_id': 'clock-1f0ebc6982b6c2d2',
            'source': 'Mic',
            'format': 'wav',
            'path': 'audio/mic.wav',
            'track_name': '1',
            'source_channels': [1],
            'channels': 1,
            'sample_rate': 48_000,
            'bit_depth': 64,
        },
    ]


def test_recorder_writes_one_record_for_all_media(
    monkeypatch: pytest.MonkeyPatch,
    mock_devices: None,
    tmp_path: Path,
) -> None:
    nodes = tmp_path / 'osc.toml'
    nodes.write_text('')
    monkeypatch.setattr(recorder, 'DevicePoller', FakePoller)
    monkeypatch.setattr(recorder, 'SourceProcess', FakeSourceProcess)
    rec = Recorder(
        Cfg(
            include=['Mic'],
            output_directory=str(tmp_path),
            osc_nodes=nodes,
            silent=True,
        )
    )
    rec._start_record()

    for medium, name in (
        ('audio', 'take.wav'),
        ('midi', 'keys.jsonl'),
        ('osc', 'x18.jsonl'),
    ):
        path = rec.session_directory / medium / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()
        values = dict(
            type='file_finished',
            timestamp='now',
            stream_id=f'{medium}:test',
            path=path.as_posix(),
        )
        if medium == 'audio':
            entry = session_record.AudioFileRecord(
                **values, format='wav', clock_id='audio'
            )
        else:
            entry = session_record.EventFileRecord(
                **values,
                media_type=medium,
                format='recs_events',
                timebase=Timebase(name='monotonic', rate=Rate(numerator=1_000_000_000)),
                start_tick=0,
                end_tick=0,
                timing_source='host_monotonic',
            )
        rec.session.write(entry)
    rec._finish_record()

    records = read_jsonl(record_path(rec))
    assert [record['path'] for record in records if 'path' in record] == [
        'audio/take.wav',
        'midi/keys.jsonl',
        'osc/x18.jsonl',
    ]
    assert not list(rec.session_directory.glob('*/*-record.jsonl'))


def test_record_records_source_frame_counts(
    monkeypatch: pytest.MonkeyPatch,
    mock_devices: None,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(recorder, 'DevicePoller', FakePoller)
    monkeypatch.setattr(recorder, 'SourceProcess', FakeSourceProcess)
    rec = Recorder(Cfg(include=['Mic'], output_directory=str(tmp_path), silent=True))
    rec._start_record()
    path = rec.session_directory / 'audio/mic.wav'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch()

    rec._receive_update(
        SourceUpdate(
            channels={'1': ChannelState(is_active=True)},
            files=[path],
            frames=512,
            source_name='Mic',
            file_records=[
                SourceFile(
                    path=path,
                    source_name='Mic',
                    track_name='1',
                    source_channels=[1],
                    channels=1,
                    sample_rate=48_000,
                    bit_depth=64,
                    start_frame=256,
                )
            ],
            file_end_frames={path: 768},
            file_spans={path: [AudioSpan(start=256, count=512)]},
            frame_count=1024,
        )
    )
    rec._finish_record()

    records = read_jsonl(record_path(rec))
    for record in records:
        record.pop('timestamp', None)
    assert records[1:4] == [
        {
            'type': 'file_started',
            'media_type': 'audio',
            'stream_id': 'audio:Mic:1',
            'clock_id': 'clock-1f0ebc6982b6c2d2',
            'source': 'Mic',
            'format': 'wav',
            'frame_count': 256,
            'path': 'audio/mic.wav',
            'track_name': '1',
            'source_channels': [1],
            'channels': 1,
            'sample_rate': 48_000,
            'bit_depth': 64,
        },
        {
            'type': 'track_started',
            'frame_count': 1024,
            'source': 'Mic',
            'track': '1',
        },
        {
            'type': 'file_finished',
            'media_type': 'audio',
            'stream_id': 'audio:Mic:1',
            'clock_id': 'clock-1f0ebc6982b6c2d2',
            'source': 'Mic',
            'format': 'wav',
            'frame_count': 768,
            'path': 'audio/mic.wav',
            'track_name': '1',
            'source_channels': [1],
            'channels': 1,
            'sample_rate': 48_000,
            'bit_depth': 64,
            'quantity_count': 512,
            'audio_spans': [{'asset_start': 0, 'start': 256, 'count': 512}],
        },
    ]


@pytest.mark.parametrize('field', ['dry_run', 'calibrate', 'silence_preview'])
def test_preview_modes_do_not_write_record(
    field: str,
    monkeypatch: pytest.MonkeyPatch,
    mock_devices: None,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(recorder, 'DevicePoller', FakePoller)
    monkeypatch.setattr(recorder, 'SourceProcess', FakeSourceProcess)
    rec = Recorder(Cfg(**{field: True}, include=['Mic'], silent=True))

    rec._start_record()
    rec._finish_record()

    assert not record_path(rec).exists()
    assert not rec._midi.session_directory.exists()


def test_silence_preview_report_recommends_thresholds(
    monkeypatch: pytest.MonkeyPatch,
    mock_devices: None,
) -> None:
    monkeypatch.setattr(recorder, 'DevicePoller', FakePoller)
    monkeypatch.setattr(recorder, 'SourceProcess', FakeSourceProcess)
    rec = Recorder(
        Cfg(silence_preview=True, include=['Mic'], preview_headroom=9, silent=True)
    )
    rec.state.update({'Mic': {'1': ChannelState(max_amp=0.5, min_amp=-0.5)}})

    assert rec._silence_preview_report() == {
        'measurements': {'Mic - 1': 6.020599913279624, '(all)': 6.020599913279624},
        'profiles': {'Mic': {'noise_floor': 15.0}},
    }


def test_card_replace_uses_new_session_without_changing_output_directory(
    monkeypatch: pytest.MonkeyPatch,
    mock_devices: None,
    tmp_path: Path,
) -> None:
    old = tmp_path / 'old-card'
    new = tmp_path / 'new-card'
    output = old / 'recs'
    old.mkdir()
    new.mkdir()
    monkeypatch.setattr(recorder, 'DevicePoller', FakePoller)
    monkeypatch.setattr(recorder, 'SourceProcess', FakeSourceProcess)
    clock = [100.0]
    monkeypatch.setattr(recorder.times, 'timestamp', lambda: clock[0])
    old_disk = recording_paths.MountedDisk(old, 'old-uuid')
    new_disk = recording_paths.MountedDisk(new, 'new-uuid')
    monkeypatch.setattr(recording_paths, 'mounted_disk', lambda path: old_disk)
    mounts = [old_disk]
    monkeypatch.setattr(recording_paths, 'mounted_disks_with_uuid', lambda: mounts)
    monkeypatch.setattr(
        recording_paths, 'mounted_record_disks', lambda: [disk.path for disk in mounts]
    )
    monkeypatch.setattr(
        disk_space.shutil, 'disk_usage', lambda path: DiskUsage(100, 0, 100)
    )
    rec = Recorder(
        Cfg(
            include=['Mic'],
            output_directory=str(output),
            disk_removable_emergency=['1'],
            silent=True,
        )
    )
    rec._start_record()
    old_record = rec._record_path()

    result = rec._card_replace()

    assert result.old_uuid == 'old-uuid'
    assert rec.cfg.directory.output_directory == str(output)
    assert not rec._devices.writing_enabled
    assert rec.awaiting_card is not None
    assert rec.awaiting_card.value
    assert rec._control.status_snapshot().errors == [rec.awaiting_card]
    assert session_record.read(old_record).events[-1].type == 'card_replace_started'

    mounts[:] = [new_disk]
    clock[0] = 101.0

    assert not rec._monitor_card_replacement()
    assert rec.cfg.directory.output_directory == str(output)
    assert rec.session_directory.parent == new / 'recs'
    assert rec._devices.writing_enabled
    assert rec.awaiting_card is not None
    assert not rec.awaiting_card.value
    assert rec._control.status_snapshot().errors == [rec.awaiting_card]


def test_unmounted_recording_disk_starts_card_replacement(
    monkeypatch: pytest.MonkeyPatch,
    mock_devices: None,
    tmp_path: Path,
) -> None:
    old = tmp_path / 'old-card'
    output = old / 'recs'
    old.mkdir()
    monkeypatch.setattr(recorder, 'DevicePoller', FakePoller)
    monkeypatch.setattr(recorder, 'SourceProcess', FakeSourceProcess)
    rec = Recorder(Cfg(include=['Mic'], output_directory=str(output), silent=True))
    old_disk = recording_paths.MountedDisk(old, 'old-uuid')
    rec._recording_disk = old_disk
    monkeypatch.setattr(recording_paths, 'mounted_disks_with_uuid', lambda: [])

    rec._record_write_error('Mic', 'Input/output error')

    assert rec._card_replacement.active
    assert rec._card_replacement.use_old_mount_immediately
    assert not rec._devices.writing_enabled
    assert rec.awaiting_card is not None
    assert rec.awaiting_card.value


def test_card_replacement_uses_mounted_disk_with_emergency_reserve(
    monkeypatch: pytest.MonkeyPatch,
    mock_devices: None,
    tmp_path: Path,
) -> None:
    old = tmp_path / 'old-card'
    new = tmp_path / 'new-card'
    output = old / 'recs'
    old.mkdir()
    new.mkdir()
    monkeypatch.setattr(recorder, 'DevicePoller', FakePoller)
    monkeypatch.setattr(recorder, 'SourceProcess', FakeSourceProcess)
    monkeypatch.setattr(recording_paths, 'mounted_record_disks', lambda: [old, new])
    monkeypatch.setattr(
        disk_space.shutil,
        'disk_usage',
        lambda path: DiskUsage(
            100,
            10 if Path(path) == new else 90,
            90 if Path(path) == new else 10,
        ),
    )
    now = [100.0]
    monkeypatch.setattr(recorder.times, 'timestamp', lambda: now[0])
    old_disk = recording_paths.MountedDisk(old, 'old-uuid')
    new_disk = recording_paths.MountedDisk(new, 'new-uuid')
    monkeypatch.setattr(recording_paths, 'mounted_disk', lambda path: old_disk)
    monkeypatch.setattr(
        recording_paths, 'mounted_disks_with_uuid', lambda: [old_disk, new_disk]
    )
    rec = Recorder(
        Cfg(
            include=['Mic'],
            output_directory=str(output),
            disk_removable_emergency=['50'],
            silent=True,
        )
    )
    rec._start_record()

    rec._card_replace()

    assert rec.session_directory.parent == new / 'recs'
    assert rec.awaiting_card is not None
    assert not rec.awaiting_card.value


def test_new_session_links_records_and_keeps_device_timeline(
    monkeypatch: pytest.MonkeyPatch,
    mock_devices: None,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(recorder, 'DevicePoller', FakePoller)
    monkeypatch.setattr(recorder, 'SourceProcess', FakeSourceProcess)
    monkeypatch.setattr(
        recorder.connection,
        'wait',
        lambda connections, timeout: [c for c in connections if c.poll()],
    )
    clock = [100.0]
    monkeypatch.setattr(recorder.times, 'timestamp', lambda: clock[0])
    rec = Recorder(Cfg(include=['Mic'], output_directory=str(tmp_path), silent=True))
    rec._start_record()
    source = rec._devices.hardware['Mic']
    source.start()
    old_record_path = rec._record_path()
    old_session_id = rec.session.session_id
    old_audio_path = rec.session_directory / 'audio/old.flac'
    old_audio_path.parent.mkdir()
    old_audio_path.write_bytes(b'audio')
    source.connection.messages.append(
        SourceUpdate(
            channels={},
            files=[old_audio_path],
            frames=48_000,
            source_name='Mic',
            file_records=[
                SourceFile(
                    path=old_audio_path,
                    source_name='Mic',
                    track_name='1',
                    source_channels=[1],
                    channels=1,
                    sample_rate=48_000,
                    bit_depth=16,
                    start_frame=0,
                    start_timestamp=99.0,
                )
            ],
            file_end_frames={old_audio_path: 48_000},
            file_end_timestamps={old_audio_path: 100.0},
            frame_count=48_000,
            writing_enabled=False,
        )
    )

    request = FakeControlRequest(gui_protocol.NewSession(type='new_session'))
    rec.live = FakeControlDisplay([request])

    rec._receive_control_requests()

    result = request.responses[0]
    assert isinstance(result, gui_protocol.NewSessionStarted)
    new_record_path = Path(result.record_path)
    old_record = session_record.read(old_record_path)
    new_record = session_record.read(new_record_path)
    continuation = next(
        event for event in old_record.events if event.type == 'session_continued_at'
    )
    assert result.session_id != old_session_id
    assert source.start_count == 1
    assert source.is_alive
    assert rec._devices.writing_enabled
    assert rec._devices.frames['Mic'] == 48_000
    assert continuation.continued_at is not None
    assert (old_record_path.parent / continuation.continued_at).resolve() == (
        new_record_path.resolve()
    )
    assert new_record.continued_from is not None
    assert (new_record_path.parent / new_record.continued_from).resolve() == (
        old_record_path.resolve()
    )

    new_audio_path = rec.session_directory / 'audio/new.flac'
    new_audio_path.parent.mkdir()
    new_audio_path.write_bytes(b'audio')
    rec._receive_update(
        SourceUpdate(
            channels={},
            files=[new_audio_path],
            frames=512,
            source_name='Mic',
            file_records=[
                SourceFile(
                    path=new_audio_path,
                    source_name='Mic',
                    track_name='1',
                    source_channels=[1],
                    channels=1,
                    sample_rate=48_000,
                    bit_depth=16,
                    start_frame=48_000,
                    start_timestamp=100.0,
                )
            ],
            file_end_frames={new_audio_path: 48_512},
            file_end_timestamps={new_audio_path: 100.01},
            frame_count=48_512,
        )
    )
    new_record = session_record.read(new_record_path)

    assert new_record.files[-1].frame_count == 48_000


def test_identical_warnings_are_aggregated(
    monkeypatch: pytest.MonkeyPatch,
    mock_devices: None,
    caplog: pytest.LogCaptureFixture,
) -> None:
    timestamps = iter([0.0, 100.0, 101.0])
    monkeypatch.setattr(recorder, 'DevicePoller', FakePoller)
    monkeypatch.setattr(recorder, 'SourceProcess', FakeSourceProcess)
    monkeypatch.setattr(recorder.times, 'timestamp', lambda: next(timestamps))
    rec = Recorder(Cfg(include=['Mic'], silent=True))
    entries: list[session_record.Record] = []
    rec.session.write = entries.append

    rec._record_warning('Device Mic failed')
    rec._record_warning('Device Mic failed')
    rec._flush_warning_summaries()

    assert rec.error_records() == [
        ErrorRecord(
            timestamp='1970-01-01T00:01:41.000Z',
            message='Device Mic failed',
            first_timestamp='1970-01-01T00:01:40.000Z',
            count=2,
        )
    ]
    assert entries == [
        session_record.WarningRecord(
            timestamp='1970-01-01T00:01:40.000Z',
            message='Device Mic failed',
        ),
        session_record.WarningRecord(
            timestamp='1970-01-01T00:01:41.000Z',
            message='Device Mic failed',
            first_timestamp='1970-01-01T00:01:40.000Z',
            count=2,
        ),
    ]
    assert caplog.messages == ['Device Mic failed']


def test_buffer_overflow_records_write_latency(
    monkeypatch: pytest.MonkeyPatch,
    mock_devices: None,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(recorder, 'DevicePoller', FakePoller)
    monkeypatch.setattr(recorder, 'SourceProcess', FakeSourceProcess)
    rec = Recorder(Cfg(include=['Mic'], output_directory=str(tmp_path), silent=True))
    rec._start_record()

    rec._record_device_buffer_update(
        'Mic',
        BufferStats(
            dropped_blocks=1,
            dropped_frames=2,
            last_drop_timestamp=3.0,
            max_write_seconds=0.25,
        ),
    )

    records = read_jsonl(record_path(rec))
    assert records[1]['type'] == 'buffer_overflow'
    assert records[1]['max_write_seconds'] == 0.25


def test_empty_template_output_directory_record_uses_time_template(
    monkeypatch: pytest.MonkeyPatch,
    mock_devices: None,
    tmp_path: Path,
) -> None:
    timestamp = datetime(2026, 6, 23, 20, 34, 10).timestamp()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(recorder.times, 'timestamp', lambda: timestamp)
    monkeypatch.setattr(recorder, 'DevicePoller', FakePoller)
    monkeypatch.setattr(recorder, 'SourceProcess', FakeSourceProcess)
    rec = Recorder(Cfg(include=['Mic'], output_directory='sessions/{sdate}'))
    rec._start_record()

    assert Path('sessions/2026/06/23/2026-06-23 20-34-10/session-record.jsonl').exists()


def test_default_output_directory_uses_session_timestamp(
    monkeypatch: pytest.MonkeyPatch,
    mock_devices: None,
    tmp_path: Path,
) -> None:
    timestamp = datetime(2026, 6, 23, 20, 34, 10).timestamp()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(recorder.times, 'timestamp', lambda: timestamp)
    monkeypatch.setattr(recorder, 'SourceProcess', FakeSourceProcess)

    rec = Recorder(Cfg(include=['Mic'], silent=True))
    rec._start_record()
    expected = recording_paths.session_directory_name(timestamp)
    path = rec.session_directory / 'audio/mic.wav'
    path.parent.mkdir(exist_ok=True, parents=True)
    path.touch()

    rec._receive_update(
        SourceUpdate(
            channels={'1': ChannelState()},
            files=[path],
            frames=48_000,
            source_name='Mic',
            file_records=[
                SourceFile(
                    path=path,
                    source_name='Mic',
                    track_name='1',
                    source_channels=[1],
                    channels=1,
                    sample_rate=48_000,
                    bit_depth=64,
                )
            ],
        )
    )
    rec._finish_record()

    assert rec.cfg.directory.output_directory == ''
    assert rec.session_directory == Path(expected)
    assert (rec.session_directory / 'session-record.jsonl').exists()


def test_default_output_directory_uses_collision_suffix(
    monkeypatch: pytest.MonkeyPatch,
    mock_devices: None,
    tmp_path: Path,
) -> None:
    timestamp = datetime(2026, 6, 23, 20, 34, 10).timestamp()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(recorder.times, 'timestamp', lambda: timestamp)
    monkeypatch.setattr(recorder, 'SourceProcess', FakeSourceProcess)
    expected = recording_paths.session_directory_name(timestamp)
    Path(expected).mkdir()

    rec = Recorder(Cfg(include=['Mic'], silent=True))

    assert rec.cfg.directory.output_directory == ''
    assert rec.session_directory == Path(f'{expected}_1')


def test_daemon_default_output_directory_uses_largest_external_disk(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    small = tmp_path / 'small'
    large = tmp_path / 'large'
    monkeypatch.setattr(recorder.gui_ipc, 'daemon_mode_enabled', lambda: True)
    monkeypatch.setattr(recording_paths, 'mounted_record_disks', lambda: [small, large])
    monkeypatch.setattr(
        recording_paths.shutil,
        'disk_usage',
        lambda p: DiskUsage(100, 50, 10 if p == small else 90),
    )

    timestamp = datetime(2026, 6, 23, 20, 34, 10).timestamp()
    cfg = recording_paths.with_default_output_directory(
        Cfg(default_record_directory='takes'), timestamp
    )

    assert cfg.directory.output_directory == str(large / 'takes')
    assert recording_paths.session_directory(str(large / 'takes'), timestamp) == (
        large / 'takes' / '2026-06-23 20-34-10'
    )
    assert recording_paths.media_session_directory(
        large / 'takes' / '2026-06-23 20-34-10', 'midi'
    ) == (large / 'takes' / '2026-06-23 20-34-10' / 'midi')


def test_daemon_default_output_directory_falls_back_to_system_disk(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(recorder.gui_ipc, 'daemon_mode_enabled', lambda: True)
    monkeypatch.setattr(recording_paths, 'mounted_record_disks', lambda: [])
    monkeypatch.setattr(recording_paths.Path, 'home', lambda: tmp_path)

    timestamp = datetime(2026, 6, 23, 20, 34, 10).timestamp()
    cfg = recording_paths.with_default_output_directory(Cfg(), timestamp)

    assert cfg.directory.output_directory == str(tmp_path / 'recs')


def test_daemon_default_output_directory_keeps_explicit_directory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(recorder.gui_ipc, 'daemon_mode_enabled', lambda: True)

    cfg = recording_paths.with_default_output_directory(
        Cfg(output_directory='manual'), 0
    )

    assert cfg.directory.output_directory == 'manual'


def test_default_output_directory_replaces_problematic_characters() -> None:
    timestamp = datetime(2026, 6, 23, 20, 34, 10).timestamp()

    assert recording_paths.session_directory_name(timestamp) == '2026-06-23 20-34-10'


def test_record_records_source_and_track_lifecycle_events(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    now = 100.0

    def timestamp() -> float:
        nonlocal now
        now += 1.0
        return now

    monkeypatch.setattr(recorder.times, 'timestamp', timestamp)
    monkeypatch.setattr(recorder, 'DevicePoller', FakePoller)
    monkeypatch.setattr(recorder, 'SourceProcess', FakeSourceProcess)
    rec = Recorder(
        Cfg(
            devices=Path(DEVICES_FILE),
            include=['Mic'],
            output_directory=str(tmp_path),
            silent=True,
        )
    )
    rec._start_record()
    mic_info = next(info for info in DEVICES if info['name'] == 'Mic')
    rec._devices.poller.snapshots = [{'Mic': mic_info}, {}, {'Mic': mic_info}]

    rec._poll_devices()
    rec._receive_update(
        SourceUpdate(
            channels={'1': ChannelState(is_active=True)},
            files=[],
            frames=48_000,
            source_name='Mic',
        )
    )
    rec._receive_update(
        SourceUpdate(
            channels={'1': ChannelState(is_active=False)},
            files=[],
            frames=240_000,
            source_name='Mic',
        )
    )
    rec._poll_devices()
    rec._reap_sources()
    rec._poll_devices()
    records = read_jsonl(record_path(rec))
    assert records[1:] == [
        {
            'timestamp': '1970-01-01T00:01:43.000Z',
            'type': 'source_online',
            'source': 'Mic',
            'start_frame': 0,
        },
        {
            'timestamp': '1970-01-01T00:01:44.000Z',
            'type': 'track_started',
            'source': 'Mic',
            'track': '1',
        },
        {
            'timestamp': '1970-01-01T00:01:46.000Z',
            'type': 'track_stopped',
            'source': 'Mic',
            'track': '1',
        },
        {
            'timestamp': '1970-01-01T00:01:48.000Z',
            'type': 'warning',
            'message': 'Device Mic went offline',
        },
        {
            'timestamp': '1970-01-01T00:01:49.000Z',
            'type': 'source_offline',
            'source': 'Mic',
        },
        {
            'timestamp': '1970-01-01T00:01:51.000Z',
            'type': 'source_online',
            'source': 'Mic',
            'start_frame': 288000,
        },
    ]


def test_record_records_key_events(
    monkeypatch: pytest.MonkeyPatch,
    mock_devices: None,
    tmp_path: Path,
) -> None:
    now = 100.0

    def timestamp() -> float:
        nonlocal now
        now += 1.0
        return now

    monkeypatch.setattr(recorder.times, 'timestamp', timestamp)
    monkeypatch.setattr(recorder, 'DevicePoller', FakePoller)
    monkeypatch.setattr(recorder, 'SourceProcess', FakeSourceProcess)
    rec = Recorder(
        Cfg(
            key_label=['g=guitar too soft'],
            output_directory=str(tmp_path),
            silent=True,
        )
    )
    rec._start_record()
    rec.key_recorder = FakeKeyRecorder(
        [
            KeyEvent(type='key_pressed', key='g'),
            KeyEvent(type='key_released', key='g'),
        ]
    )

    rec._receive_key_events()
    records = read_jsonl(record_path(rec))
    assert [r for r in records if r['type'].startswith('key_')] == [
        {
            'timestamp': '1970-01-01T00:01:42.000Z',
            'type': 'key_pressed',
            'key': 'g',
            'label': 'guitar too soft',
        },
        {
            'timestamp': '1970-01-01T00:01:43.000Z',
            'type': 'key_released',
            'key': 'g',
            'label': 'guitar too soft',
        },
    ]
