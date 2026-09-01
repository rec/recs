from pathlib import Path

import tomlkit
from pytest import MonkeyPatch

from recs.ui import recovery_report


def test_writes_recovery_report_beside_unfinished_record(
    monkeypatch: MonkeyPatch, tmp_path: Path
) -> None:
    session = tmp_path / 'session'
    audio = session / 'audio'
    audio.mkdir(parents=True)
    (audio / 'open.wav').write_bytes(b'audio')
    record = session / 'session-record.jsonl'
    record.write_text(
        '{"type":"header","version":3,"started_at":"start"}\n'
        '{"type":"file_started","media_type":"audio","stream_id":"audio:test:1","format":"wav","timestamp":"file-start",'
        '"path":"audio/open.wav","track":1,"channels":1,'
        '"sample_rate":48000,"bit_depth":32}\n'
        '{"type":"file_started","media_type":"audio","stream_id":"audio:test:1","format":"wav","timestamp":"missing-start",'
        '"path":"audio/missing.wav","track":1,"channels":1,'
        '"sample_rate":48000,"bit_depth":32}\n'
        '{"type":"source_update","timestamp":"source-update",'
        '"source":"Mic"}\n'
        '{"type":"disk_emergency","timestamp":"disk-event",'
        '"disk":"/mnt/openloop","free_bytes":10}\n'
    )
    messages: list[str] = []
    monkeypatch.setattr(
        recovery_report.LOGGER,
        'error',
        lambda message, *arguments: messages.append(message % arguments),
    )

    reports = recovery_report.report_unfinished_sessions(tmp_path)

    report_path = session / 'recs-recovery-report.toml'
    assert reports == [report_path]
    assert messages == [
        f'Unfinished session, 2 open files, 1 missing file: see {report_path.resolve()}'
    ]
    report = tomlkit.parse(report_path.read_text())
    assert report['record'] == str(record.resolve())
    assert report['last_record_type'] == 'disk_emergency'
    assert report['open_files'] == ['audio/missing.wav', 'audio/open.wav']
    assert report['missing_files'] == ['audio/missing.wav']
    assert report['sources'] == [
        {
            'source': 'Mic',
            'last_event_type': 'source_update',
            'last_timestamp': 'source-update',
        }
    ]
    assert report['disk'] == {
        'event_type': 'disk_emergency',
        'timestamp': 'disk-event',
        'disk': '/mnt/openloop',
        'free_bytes': 10,
    }
    assert report['tracks'] == [
        {
            'media_type': 'audio',
            'track': 1,
            'started_files': 2,
            'finished_files': 0,
            'open_files': 2,
            'missing_files': 1,
            'likely_complete': False,
        }
    ]


def test_skips_finished_record(monkeypatch: MonkeyPatch, tmp_path: Path) -> None:
    directory = tmp_path / 'session'
    directory.mkdir(parents=True)
    record = directory / 'session-record.jsonl'
    record.write_text(
        '{"type":"header","version":3,"started_at":"start"}\n'
        '{"type":"footer","ended_at":"end","duration_seconds":1}\n'
    )
    messages: list[str] = []
    monkeypatch.setattr(
        recovery_report.LOGGER,
        'error',
        lambda message, *arguments: messages.append(message % arguments),
    )

    reports = recovery_report.report_unfinished_sessions(tmp_path)

    assert reports == []
    assert messages == []
    assert not (directory / 'recs-recovery-report.toml').exists()


def test_ignores_osc_data_file_named_record(tmp_path: Path) -> None:
    directory = tmp_path / 'session/osc'
    directory.mkdir(parents=True)
    (directory / 'lighting-record.jsonl').write_text(
        '{"kind":"packet","timestamp":"event"}\n'
    )

    assert recovery_report.report_unfinished_sessions(tmp_path) == []
    assert not (directory / 'recs-recovery-report.toml').exists()
