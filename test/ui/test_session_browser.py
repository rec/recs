import json
from pathlib import Path

from recs.ui import session_browser


def test_session_browser_lists_session_records(
    capsys,
    tmp_path: Path,
) -> None:
    session = _record(tmp_path)

    assert session_browser.main([str(tmp_path)]) == 0

    assert capsys.readouterr().out == (
        f'start  audio=1  midi=1  bytes=8  {session.as_posix()}\n'
    )


def test_session_browser_lists_session_records_as_json(
    capsys,
    tmp_path: Path,
) -> None:
    session = _record(tmp_path)

    assert session_browser.main(['--json', str(tmp_path)]) == 0

    data = json.loads(capsys.readouterr().out)
    assert data == [
        {
            'path': session.as_posix(),
            'started_at': 'start',
            'ended_at': 'end',
            'duration': 1.5,
            'output_directories': [
                (session / 'audio').as_posix(),
                (session / 'midi').as_posix(),
            ],
            'devices': ['Mic'],
            'tracks': ['Mic:1'],
            'midi_ports': ['Launchkey'],
            'files': 2,
            'audio_files': 1,
            'midi_files': 1,
            'midi_messages': 3,
            'total_bytes': 8,
            'warnings': ['quiet'],
            'disk_events': 1,
            'markers': 2,
            'continued_from': None,
            'continued_at': ['next/audio-record.jsonl'],
        }
    ]


def test_session_browser_ignores_invalid_records(tmp_path: Path) -> None:
    directory = tmp_path / 'session/audio'
    directory.mkdir(parents=True)
    record = directory / 'audio-record.jsonl'
    record.write_text('{')

    assert session_browser.scan(tmp_path) == []


def test_session_browser_shows_one_session(
    capsys,
    tmp_path: Path,
) -> None:
    session = _record(tmp_path)

    assert session_browser.main(['show', str(session)]) == 0

    output = capsys.readouterr().out
    assert 'audio_files: 1\n' in output
    assert 'midi_files: 1\n' in output
    assert 'midi_messages: 3\n' in output
    assert 'midi_ports: Launchkey\n' in output


def _record(tmp_path: Path) -> Path:
    session = tmp_path / 'take'
    audio = session / 'audio'
    midi = session / 'midi'
    audio.mkdir(parents=True)
    midi.mkdir()
    (audio / 'take.wav').write_bytes(b'data')
    (midi / 'keys.mid').write_bytes(b'midi')
    (audio / 'audio-record.jsonl').write_text(
        '{"type":"header","version":2,"started_at":"start"}\n'
        '{"type":"key_pressed","timestamp":"mark","key":"g"}\n'
        '{"type":"mark","timestamp":"mark","label":"solo"}\n'
        '{"type":"disk_switch_continued_at","timestamp":"switch",'
        '"continued_at":"next/audio-record.jsonl"}\n'
        '{"type":"file_finished","timestamp":"done","path":"take.wav",'
        '"source":"Mic","track":1,"channels":1,"sample_rate":48000,'
        '"bit_depth":32}\n'
        '{"type":"warning","timestamp":"warn","message":"quiet"}\n'
        '{"type":"footer","ended_at":"end","duration":1.5}\n'
    )
    (midi / 'midi-record.jsonl').write_text(
        '{"type":"header","version":2,"started_at":"start"}\n'
        '{"type":"file_finished","kind":"midi","timestamp":"done",'
        '"path":"keys.mid","source":"Launchkey","message_count":3,'
        '"midi_port":"Launchkey","timing_source":"mido"}\n'
        '{"type":"footer","ended_at":"end","duration":1.5}\n'
    )
    return session
