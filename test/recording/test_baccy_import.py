from pathlib import Path

import numpy as np
import pytest
import soundfile

from recs.base.errors import RecsError
from recs.recording import legacy
from recs.recording.baccy_import import import_recordings
from recs.recording.read import read_recording
from recs.recording.session_record_check import check


def test_flow_import_creates_metadata_and_prints_media_moves(tmp_path: Path) -> None:
    source = tmp_path / 'source'
    audio = (
        source / 'oderg in duo/2026-04-10/14-21-31/1-2 + 142131/FLOW 8 (Recording).wav'
    )
    _write_wav(audio, channels=2)

    result = import_recordings(source, tmp_path / 'sessions')

    assert len(result) == 1
    session = result[0].session_directory
    document = read_recording(session / 'recording.toml')
    assert document.body.project_name == 'oderg in duo'
    assert audio.exists()
    assert not list((session / 'audio').iterdir())
    assert f"mv -n '{audio}'" in result[0].commands[0]

    audio.rename(session / 'audio/01-FLOW 8 (Recording).wav')

    assert check(session / 'recording.toml') == []


def test_identical_flow_copy_is_planned_once(tmp_path: Path) -> None:
    source = tmp_path / 'source'
    first = (
        source / 'oderg in duo/2026-04-10/15-33-15/1-2 + 153315/FLOW 8 (Recording).wav'
    )
    second = (
        source
        / 'oderg in duo/2026-04-10/15-33-15 copy/1-2 + 153315/FLOW 8 (Recording).wav'
    )
    _write_wav(first, channels=2)
    second.parent.mkdir(parents=True)
    second.write_bytes(first.read_bytes())

    result = import_recordings(source, tmp_path / 'sessions')

    assert len(result) == 1
    assert result[0].source_paths == [first]
    assert first.exists() and second.exists()


def test_nonidentical_flow_copy_is_rejected(tmp_path: Path) -> None:
    source = tmp_path / 'source'
    first = (
        source / 'oderg in duo/2026-04-10/15-33-15/1-2 + 153315/FLOW 8 (Recording).wav'
    )
    second = (
        source
        / 'oderg in duo/2026-04-10/15-33-15 copy/1-2 + 153315/FLOW 8 (Recording).wav'
    )
    _write_wav(first, channels=2)
    _write_wav(second, channels=1)

    with pytest.raises(RecsError, match='Non-identical duplicate'):
        import_recordings(source, tmp_path / 'sessions')

    assert not (tmp_path / 'sessions').exists()


def test_livetrak_import_plans_device_evidence_move(tmp_path: Path) -> None:
    source = tmp_path / 'source'
    take = source / 'totm/LiveTrak L-12/NO NAME/FOLDER01/251231_120000'
    _write_wav(take / 'TRACK01.WAV', channels=1)
    evidence = take / 'PRJDATA.ZDT'
    evidence.write_bytes(b'device settings')

    result = import_recordings(source, tmp_path / 'sessions')

    assert len(result) == 1
    session = result[0].session_directory
    assert session.is_relative_to(tmp_path / 'sessions/totm/2025/12/31')
    assert read_recording(session / 'recording.toml').body.project_name == 'totm'
    assert any(str(evidence) in command for command in result[0].commands)
    assert evidence.exists()


def test_legacy_recs_session_is_migrated_with_its_project(tmp_path: Path) -> None:
    source = tmp_path / 'source'
    session = source / 'oderg in duo/2026-09-04 15-01-57'
    audio = session / 'audio.wav'
    _write_wav(audio, channels=1)
    records: list[legacy.Record] = [
        legacy.SessionHeader(started_at='2026-09-04T13:01:57Z', session_id='legacy')
    ]
    for type in ('file_started', 'file_finished'):
        records.append(
            legacy.FileRecord(
                type=type,
                media_type='audio',
                timestamp='2026-09-04T13:01:57Z',
                stream_id='audio:old:1',
                format='wav',
                path='audio.wav',
                frame_count=480 if type == 'file_finished' else 0,
                quantity_count=480 if type == 'file_finished' else None,
                sample_rate=48_000,
                channels=1,
            )
        )
    records.append(
        legacy.SessionFooter(ended_at='2026-09-04T13:01:58Z', duration_seconds=1)
    )
    (session / 'session-record.jsonl').write_text(
        ''.join(record.model_dump_json(exclude_none=True) + '\n' for record in records)
    )
    (session / 'recording.toml').write_text('format = "recs"\nversion = 3\n')

    result = import_recordings(source, tmp_path / 'sessions')

    assert len(result) == 1
    imported = result[0].session_directory
    assert (
        read_recording(imported / 'recording.toml').body.project_name == 'oderg in duo'
    )
    assert any(
        'evidence/session-record-v3.jsonl' in command for command in result[0].commands
    )


def _write_wav(path: Path, *, channels: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    soundfile.write(path, np.zeros((480, channels)), 48_000)
