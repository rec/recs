import json
from pathlib import Path

from recs.ui import session_browser


def test_session_browser_lists_session_manifests(
    capsys,
    tmp_path: Path,
) -> None:
    manifest = _manifest(tmp_path)

    assert session_browser.main([str(tmp_path)]) == 0

    assert capsys.readouterr().out == (
        f'start  files=1  bytes=4  {manifest.as_posix()}\n'
    )


def test_session_browser_lists_session_manifests_as_json(
    capsys,
    tmp_path: Path,
) -> None:
    manifest = _manifest(tmp_path)

    assert session_browser.main(['--json', str(tmp_path)]) == 0

    data = json.loads(capsys.readouterr().out)
    assert data == [
        {
            'path': manifest.as_posix(),
            'started_at': 'start',
            'ended_at': 'end',
            'duration': 1.5,
            'output_directories': [(tmp_path / 'take').as_posix()],
            'devices': ['Mic'],
            'tracks': ['Mic:1'],
            'files': 1,
            'total_bytes': 4,
            'warnings': ['quiet'],
            'disk_events': 1,
            'markers': 2,
            'continued_from': None,
            'continued_at': ['next/recs-session.jsonl'],
        }
    ]


def test_session_browser_ignores_invalid_manifests(tmp_path: Path) -> None:
    manifest = tmp_path / 'recs-session.jsonl'
    manifest.write_text('{')

    assert session_browser.scan(tmp_path) == []


def test_session_browser_shows_one_session(
    capsys,
    tmp_path: Path,
) -> None:
    manifest = _manifest(tmp_path)

    assert session_browser.main(['show', str(manifest)]) == 0

    assert 'files: 1\n' in capsys.readouterr().out


def _manifest(tmp_path: Path) -> Path:
    manifest = tmp_path / 'take/recs-session.jsonl'
    manifest.parent.mkdir()
    (manifest.parent / 'take.wav').write_bytes(b'data')
    manifest.write_text(
        '{"type":"header","version":2,"started_at":"start"}\n'
        '{"type":"key_pressed","timestamp":"mark","key":"g"}\n'
        '{"type":"mark","timestamp":"mark","label":"solo"}\n'
        '{"type":"disk_switch_continued_at","timestamp":"switch",'
        '"continued_at":"next/recs-session.jsonl"}\n'
        '{"type":"file_finished","timestamp":"done","path":"take.wav",'
        '"source":"Mic","track":1,"channels":1,"sample_rate":48000,'
        '"bit_depth":32}\n'
        '{"type":"warning","timestamp":"warn","message":"quiet"}\n'
        '{"type":"footer","ended_at":"end","duration":1.5}\n'
    )
    return manifest
