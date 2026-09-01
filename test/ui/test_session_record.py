import json
from pathlib import Path

import pytest

from recs.ui import session_record
from recs.ui.session_record import EventEntry, FileEntry, SessionRecordWriter


def test_session_record_writer_batches_fsync(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    fsynced: list[int] = []
    times = iter([0.0, 0.5, 2.0, 2.0, 2.0])
    monkeypatch.setattr(session_record.os, 'fsync', fsynced.append)
    monkeypatch.setattr(session_record.time, 'monotonic', lambda: next(times))
    writer = SessionRecordWriter(tmp_path / 'session-record.jsonl', started_at='start')

    writer.write(
        EventEntry(timestamp='event', type='key_pressed', key='g'),
    )
    writer.write(
        EventEntry(timestamp='event', type='key_pressed', key='h'),
    )
    writer.close()

    lines = (tmp_path / 'session-record.jsonl').read_text().splitlines()
    assert [json.loads(line)['type'] for line in lines] == [
        'header',
        'key_pressed',
        'key_pressed',
    ]
    assert len(fsynced) == 3


def test_session_record_writer_reports_fsync_errors(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    def fail_sync(fd: int) -> None:
        raise OSError('disk is unhappy')

    monkeypatch.setattr(session_record.os, 'fsync', fail_sync)
    writer = SessionRecordWriter(tmp_path / 'session-record.jsonl', started_at='start')

    assert 'disk is unhappy' in writer.take_errors()[0]


def test_session_record_reader_ignores_truncated_final_line(tmp_path: Path) -> None:
    record = tmp_path / 'session-record.jsonl'
    record.write_text(
        '{"type":"header","version":3,"started_at":"start"}\n'
        '{"type":"key_pressed","timestamp":"event","key":"g"}\n'
        '{"type":'
    )

    result = session_record.read(record)

    assert result.started_at == 'start'
    assert result.events == [EventEntry(timestamp='event', type='key_pressed', key='g')]
    assert 'truncated final line' in result.errors[0]


def test_session_record_reader_reports_bad_nonfinal_line(tmp_path: Path) -> None:
    record = tmp_path / 'session-record.jsonl'
    record.write_text(
        '{"type":"header","version":3,"started_at":"start"}\n'
        '{"type":\n'
        '{"type":"key_pressed","timestamp":"event","key":"g"}\n'
    )

    result = session_record.read(record)

    assert result.events == [EventEntry(timestamp='event', type='key_pressed', key='g')]
    assert 'line 2' in result.errors[0]


def test_session_record_reader_keeps_file_lifecycle(tmp_path: Path) -> None:
    record = tmp_path / 'session-record.jsonl'
    record.write_text(
        '{"type":"header","version":3,"started_at":"start"}\n'
        '{"type":"file_started","media_type":"audio","stream_id":"audio:test:1","format":"wav","timestamp":"start","path":"take.wav",'
        '"track":1,"channels":1,"sample_rate":48000,"bit_depth":32}\n'
        '{"type":"file_finished","media_type":"audio","stream_id":"audio:test:1","format":"wav","timestamp":"end","path":"take.wav",'
        '"track":1,"channels":1,"sample_rate":48000,"bit_depth":32}\n'
        '{"type":"footer","ended_at":"end","duration_seconds":1}\n'
    )

    result = session_record.read(record)

    assert result.files == [
        FileEntry(
            type='file_started',
            media_type='audio',
            timestamp='start',
            stream_id='audio:test:1',
            format='wav',
            path='take.wav',
            track=1,
            channels=1,
            sample_rate=48_000,
            bit_depth=32,
        ),
        FileEntry(
            type='file_finished',
            media_type='audio',
            timestamp='end',
            stream_id='audio:test:1',
            format='wav',
            path='take.wav',
            track=1,
            channels=1,
            sample_rate=48_000,
            bit_depth=32,
        ),
    ]
    assert result.ended_at == 'end'
    assert result.duration_seconds == 1


def test_session_record_reader_accepts_user_defined_media(tmp_path: Path) -> None:
    record = tmp_path / 'session-record.jsonl'
    record.write_text(
        '{"type":"header","version":3,"started_at":"start",'
        '"metadata":{"venue":"hall"}}\n'
        '{"type":"file_finished","timestamp":"end",'
        '"stream_id":"org.example.motion:stage","media_type":'
        '"org.example.motion-capture","path":"motion.bin",'
        '"format":"org.example.motion-v1","quantity_count":3,'
        '"metadata":{"components":["x","y","z"]}}\n'
        '{"type":"footer","ended_at":"end","duration_seconds":1}\n'
    )

    result = session_record.read(record)

    assert result.metadata == {'venue': 'hall'}
    assert result.files[0].media_type == 'org.example.motion-capture'
    assert result.files[0].metadata == {'components': ['x', 'y', 'z']}
