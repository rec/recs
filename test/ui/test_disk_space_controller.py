from pathlib import Path
from test.ui.test_recorder import DiskUsage, FakePoller, FakeSourceProcess

import pytest

from recs.base.state import ChannelState
from recs.cfg.cfg import Cfg
from recs.ui import (
    disk_space,
    disk_space_controller,
    recorder,
    recording_paths,
    session_record,
)
from recs.ui.recorder import Recorder
from recs.ui.source_recorder import SourceFile, SourceUpdate


def test_minimum_free_space_is_an_emergency_reserve(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    mock_devices: None,
) -> None:
    monkeypatch.setattr(recorder, 'DevicePoller', FakePoller)
    monkeypatch.setattr(recorder, 'SourceProcess', FakeSourceProcess)
    monkeypatch.setattr(
        disk_space_controller.shutil, 'disk_usage', lambda path: DiskUsage(100, 96, 4)
    )
    rec = Recorder(Cfg(minimum_free_space=5, silent=True))

    rec._disk_space_controller.monitor_disk_space()

    assert rec._disk_space_policy.paused
    assert caplog.messages == ['Disk space emergency on .: 0.0 M free']


def test_disk_alert_switches_to_larger_removable_disk(
    monkeypatch: pytest.MonkeyPatch,
    mock_devices: None,
    tmp_path: Path,
) -> None:
    removable = tmp_path / 'removable'
    removable.mkdir()
    monkeypatch.setattr(recorder, 'DevicePoller', FakePoller)
    monkeypatch.setattr(recorder, 'SourceProcess', FakeSourceProcess)
    monkeypatch.setattr(recording_paths, 'mounted_record_disks', lambda: [removable])
    monkeypatch.setattr(recorder.times, 'timestamp', lambda: 1.0)
    monkeypatch.setattr(
        disk_space_controller.shutil,
        'disk_usage',
        lambda path: DiskUsage(
            100,
            10 if Path(path) == removable else 60,
            90 if Path(path) == removable else 40,
        ),
    )
    rec = Recorder(
        Cfg(
            disk_alert_thresholds=['50'],
            disk_removable_emergency=['5'],
            disk_system_emergency=['5'],
            output_directory=str(tmp_path),
            silent=True,
        )
    )
    rec._start_record()
    old_record = (
        rec.session.record_writer.path
        if rec.session.record_writer is not None
        else None
    )

    rec._disk_space_controller.monitor_disk_space()

    assert Path(rec.cfg.directory.output_directory).is_relative_to(removable)
    assert rec.session.record_writer is not None
    assert old_record is not None
    assert rec.session.record_writer is not None
    assert session_record.read(rec.session.record_writer.path).continued_from is None
    assert not any(
        event.type == 'disk_switch_continued_at'
        for event in session_record.read(old_record).events
    )
    assert rec.error_messages()[-1] == (
        f'Switched recording from {tmp_path} to {removable / "recs"}: '
        'new_removable_disk_has_more_space'
    )


def test_disk_switch_records_pending_source_updates_before_closing_old_record(
    monkeypatch: pytest.MonkeyPatch, mock_devices: None, tmp_path: Path
) -> None:
    removable = tmp_path / 'removable'
    removable.mkdir()
    monkeypatch.setattr(recorder, 'DevicePoller', FakePoller)
    monkeypatch.setattr(recorder, 'SourceProcess', FakeSourceProcess)
    monkeypatch.setattr(recording_paths, 'mounted_record_disks', lambda: [removable])
    monkeypatch.setattr(recorder.times, 'timestamp', lambda: 1.0)
    monkeypatch.setattr(
        disk_space_controller.shutil,
        'disk_usage',
        lambda path: DiskUsage(
            100,
            10 if Path(path) == removable else 60,
            90 if Path(path) == removable else 40,
        ),
    )
    rec = Recorder(
        Cfg(
            disk_alert_thresholds=['50'],
            disk_removable_emergency=['5'],
            disk_system_emergency=['5'],
            output_directory=str(tmp_path),
            silent=True,
        )
    )
    rec._start_record()
    recorded = rec.session_directory / 'audio/late.wav'
    recorded.parent.mkdir()
    recorded.write_bytes(b'audio')
    old_record = (
        rec.session.record_writer.path
        if rec.session.record_writer is not None
        else None
    )
    assert old_record is not None
    rec._devices.hardware['Mic'].pending_updates.append(
        SourceUpdate(
            channels={'1': ChannelState()},
            files=[recorded],
            frames=512,
            source_name='Mic',
            file_records=[
                SourceFile(
                    path=recorded,
                    source_name='Mic',
                    track=1,
                    channels=1,
                    sample_rate=48_000,
                    bit_depth=32,
                    start_frame=0,
                    start_timestamp=1.0,
                )
            ],
            file_end_frames={recorded: 512},
            file_end_timestamps={recorded: 1.1},
            frame_count=512,
            timestamp=1.1,
        )
    )

    rec._disk_space_controller.monitor_disk_space()

    record = session_record.read(old_record)
    assert any(file.path == 'audio/late.wav' for file in record.files)


def test_disk_emergency_pauses_recording(
    monkeypatch: pytest.MonkeyPatch, mock_devices: None, tmp_path: Path
) -> None:
    monkeypatch.setattr(recorder, 'DevicePoller', FakePoller)
    monkeypatch.setattr(recorder, 'SourceProcess', FakeSourceProcess)
    monkeypatch.setattr(recording_paths, 'mounted_record_disks', lambda: [])
    monkeypatch.setattr(recorder.times, 'timestamp', lambda: 1.0)
    monkeypatch.setattr(
        disk_space_controller.shutil, 'disk_usage', lambda path: DiskUsage(100, 96, 4)
    )
    rec = Recorder(
        Cfg(
            disk_removable_emergency=['5'],
            disk_system_emergency=['5'],
            output_directory=str(tmp_path),
            silent=True,
        )
    )
    rec._start_record()

    rec._disk_space_controller.monitor_disk_space()

    assert rec._control.recording_paused
    assert rec._disk_space_policy.paused


def test_disk_emergency_pauses_when_removable_switch_fails(
    monkeypatch: pytest.MonkeyPatch, mock_devices: None, tmp_path: Path
) -> None:
    removable = tmp_path / 'removable'
    removable.mkdir()
    monkeypatch.setattr(recorder, 'DevicePoller', FakePoller)
    monkeypatch.setattr(recorder, 'SourceProcess', FakeSourceProcess)
    monkeypatch.setattr(recording_paths, 'mounted_record_disks', lambda: [removable])
    monkeypatch.setattr(recorder.times, 'timestamp', lambda: 1.0)
    monkeypatch.setattr(
        disk_space_controller.shutil,
        'disk_usage',
        lambda path: DiskUsage(
            100,
            10 if Path(path) == removable else 96,
            90 if Path(path) == removable else 4,
        ),
    )
    rec = Recorder(
        Cfg(
            disk_removable_emergency=['5'],
            disk_system_emergency=['5'],
            output_directory=str(tmp_path),
            silent=True,
        )
    )
    rec._start_record()
    attempts: list[Path] = []

    def failed_switch(disk: disk_space.Disk, reason: str) -> bool:
        attempts.append(disk.path)
        return False

    monkeypatch.setattr(
        rec._disk_space_controller, 'switch_recording_disk', failed_switch
    )

    rec._disk_space_controller.monitor_disk_space()

    assert attempts == [removable]
    assert rec._control.recording_paused
    assert rec._disk_space_policy.paused


def test_disk_pause_resumes_on_removable_disk(
    monkeypatch: pytest.MonkeyPatch, mock_devices: None, tmp_path: Path
) -> None:
    removable = tmp_path / 'removable'
    removable.mkdir()
    mounts: list[Path] = []
    monkeypatch.setattr(recorder, 'DevicePoller', FakePoller)
    monkeypatch.setattr(recorder, 'SourceProcess', FakeSourceProcess)
    monkeypatch.setattr(recording_paths, 'mounted_record_disks', lambda: mounts)
    monkeypatch.setattr(
        disk_space_controller.shutil, 'disk_usage', lambda path: DiskUsage(100, 10, 90)
    )
    now = [1.0]
    monkeypatch.setattr(recorder.times, 'timestamp', lambda: now[0])
    rec = Recorder(
        Cfg(
            disk_removable_emergency=['5'],
            disk_system_emergency=['95'],
            output_directory=str(tmp_path),
            silent=True,
        )
    )
    rec._start_record()
    rec._disk_space_controller.monitor_disk_space()
    assert rec._disk_space_policy.paused

    mounts.append(removable)
    now[0] = 2.0
    rec._disk_space_controller.monitor_disk_space()

    assert not rec._disk_space_policy.paused
    assert not rec._control.recording_paused
    assert Path(rec.cfg.directory.output_directory).is_relative_to(removable)
