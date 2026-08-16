from pathlib import Path
from test.ui.test_recorder import DiskUsage, FakePoller, FakeSourceProcess

import pytest

from recs.base.state import ChannelState
from recs.cfg.cfg import Cfg
from recs.ui import disk_control, recorder, recording_paths, session_manifest
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
        disk_control.shutil, 'disk_usage', lambda path: DiskUsage(100, 96, 4)
    )
    rec = Recorder(Cfg(minimum_free_space=5, silent=True))

    rec.disk_control.monitor_disk_space()

    assert rec.disk_monitor.paused
    assert caplog.messages == ['Disk space emergency on .: 4 bytes free']


def test_disk_alert_switches_to_larger_removable_disk(
    monkeypatch: pytest.MonkeyPatch, mock_devices: None, tmp_path: Path
) -> None:
    removable = tmp_path / 'removable'
    removable.mkdir()
    monkeypatch.setattr(recorder, 'DevicePoller', FakePoller)
    monkeypatch.setattr(recorder, 'SourceProcess', FakeSourceProcess)
    monkeypatch.setattr(recording_paths, 'mounted_record_disks', lambda: [removable])
    monkeypatch.setattr(recorder.times, 'timestamp', lambda: 1.0)
    monkeypatch.setattr(
        disk_control.shutil,
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
    rec._start_manifest()
    old_manifest = (
        rec.session.manifest.path if rec.session.manifest is not None else None
    )

    rec.disk_control.monitor_disk_space()

    assert Path(rec.cfg.directory.output_directory).is_relative_to(removable)
    assert rec.session.manifest is not None
    assert rec.session.continued_from is None
    assert old_manifest is not None
    assert rec.session.manifest is not None
    assert session_manifest.read(rec.session.manifest.path).continued_from == str(
        old_manifest
    )
    assert any(
        event.type == 'disk_switch_continued_at'
        and event.continued_at == str(rec.session.manifest.path)
        for event in session_manifest.read(old_manifest).events
    )


def test_disk_switch_records_pending_source_updates_before_closing_old_manifest(
    monkeypatch: pytest.MonkeyPatch, mock_devices: None, tmp_path: Path
) -> None:
    removable = tmp_path / 'removable'
    removable.mkdir()
    recorded = tmp_path / 'late.wav'
    recorded.write_bytes(b'audio')
    monkeypatch.setattr(recorder, 'DevicePoller', FakePoller)
    monkeypatch.setattr(recorder, 'SourceProcess', FakeSourceProcess)
    monkeypatch.setattr(recording_paths, 'mounted_record_disks', lambda: [removable])
    monkeypatch.setattr(recorder.times, 'timestamp', lambda: 1.0)
    monkeypatch.setattr(
        disk_control.shutil,
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
    rec._start_manifest()
    old_manifest = (
        rec.session.manifest.path if rec.session.manifest is not None else None
    )
    assert old_manifest is not None
    rec.hardware['Mic'].pending_updates.append(
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

    rec.disk_control.monitor_disk_space()

    manifest = session_manifest.read(old_manifest)
    assert any(Path(file.path) == recorded for file in manifest.files)


def test_disk_emergency_pauses_recording(
    monkeypatch: pytest.MonkeyPatch, mock_devices: None, tmp_path: Path
) -> None:
    monkeypatch.setattr(recorder, 'DevicePoller', FakePoller)
    monkeypatch.setattr(recorder, 'SourceProcess', FakeSourceProcess)
    monkeypatch.setattr(recording_paths, 'mounted_record_disks', lambda: [])
    monkeypatch.setattr(recorder.times, 'timestamp', lambda: 1.0)
    monkeypatch.setattr(
        disk_control.shutil, 'disk_usage', lambda path: DiskUsage(100, 96, 4)
    )
    rec = Recorder(
        Cfg(
            disk_removable_emergency=['5'],
            disk_system_emergency=['5'],
            output_directory=str(tmp_path),
            silent=True,
        )
    )
    rec._start_manifest()

    rec.disk_control.monitor_disk_space()

    assert rec.recording_paused
    assert rec.disk_monitor.paused


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
        disk_control.shutil, 'disk_usage', lambda path: DiskUsage(100, 10, 90)
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
    rec._start_manifest()
    rec.disk_control.monitor_disk_space()
    assert rec.disk_monitor.paused

    mounts.append(removable)
    now[0] = 2.0
    rec.disk_control.monitor_disk_space()

    assert not rec.disk_monitor.paused
    assert not rec.recording_paused
    assert Path(rec.cfg.directory.output_directory).is_relative_to(removable)
