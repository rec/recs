from pathlib import Path

import tomlkit

from recs.ui import session_export, session_record, session_record_check


def test_export_copies_linked_records_and_rewrites_links(tmp_path: Path) -> None:
    first = tmp_path / 'disk-a/session-a/session-record.jsonl'
    second = tmp_path / 'disk-b/session-b/session-record.jsonl'
    first_audio = first.parent / 'audio/first.flac'
    second_audio = second.parent / 'audio/second.flac'
    first_audio.parent.mkdir(parents=True)
    second_audio.parent.mkdir(parents=True)
    first_audio.write_bytes(b'first audio')
    second_audio.write_bytes(b'second audio')
    first_writer = session_record.SessionRecordWriter(
        first, started_at='first', session_id='first-session'
    )
    first_writer.write(_file('file_started', 'audio/first.flac', 'first'))
    first_writer.write(_file('file_finished', 'audio/first.flac', 'first'))
    first_writer.write(
        session_record.EventRecord(
            type='session_continued_at',
            timestamp='boundary',
            continued_at='../../disk-b/session-b/session-record.jsonl',
        )
    )
    first_writer.write(
        session_record.SessionFooter(ended_at='boundary', duration_seconds=1)
    )
    first_writer.close()
    second_writer = session_record.SessionRecordWriter(
        second,
        started_at='second',
        session_id='second-session',
        continued_from='../../disk-a/session-a/session-record.jsonl',
    )
    second_writer.write(_file('file_started', 'audio/second.flac', 'second'))
    second_writer.write(_file('file_finished', 'audio/second.flac', 'second'))
    second_writer.write(
        session_record.SessionFooter(ended_at='end', duration_seconds=1)
    )
    second_writer.close()
    destination = tmp_path / 'export'

    result = session_export.export(first, destination)

    records = sorted(result.glob('sessions/*/session-record.jsonl'))
    assert len(records) == 2
    exported = {session_record.read(p).session_id: p for p in records}
    first_export = exported['first-session']
    second_export = exported['second-session']
    first_record = session_record.read(first_export)
    second_record = session_record.read(second_export)
    assert (first_export.parent / first_record.events[-1].continued_at).resolve() == (
        second_export.resolve()
    )
    assert (second_export.parent / second_record.continued_from).resolve() == (
        first_export.resolve()
    )
    assert (first_export.parent / 'audio/first.flac').read_bytes() == b'first audio'
    assert (second_export.parent / 'audio/second.flac').read_bytes() == b'second audio'
    assert session_record_check.check(first_export) == []
    assert session_record_check.check(second_export) == []
    summary = tomlkit.parse((result / 'export-summary.toml').read_text())
    assert summary['record_count'] == 2
    assert summary['file_count'] == 2
    assert summary['total_bytes'] == len(b'first audio') + len(b'second audio')


def _file(type: str, path: str, stream: str) -> session_record.FileRecord:
    return session_record.FileRecord(
        type=type,
        media_type='audio',
        timestamp='start',
        stream_id=stream,
        format='flac',
        path=path,
    )
