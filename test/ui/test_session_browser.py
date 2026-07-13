import json
from pathlib import Path

from recs.ui import session_browser


def test_session_browser_lists_session_manifests(
    capsys,
    tmp_path: Path,
) -> None:
    manifest = tmp_path / 'take/recs-session.jsonl'
    manifest.parent.mkdir()
    manifest.write_text(
        '{"type":"header","version":2,"started_at":"start"}\n'
        '{"type":"key_pressed","timestamp":"mark","key":"g"}\n'
        '{"type":"file_finished","timestamp":"done","path":"take.wav",'
        '"track":1,"channels":1,"sample_rate":48000,"bit_depth":32}\n'
        '{"type":"warning","timestamp":"warn","message":"quiet"}\n'
        '{"type":"footer","ended_at":"end","duration":1.5}\n'
    )

    assert session_browser.main([str(tmp_path)]) == 0

    data = json.loads(capsys.readouterr().out)
    assert data == [
        {
            'path': manifest.as_posix(),
            'started_at': 'start',
            'ended_at': 'end',
            'duration': 1.5,
            'files': 1,
            'warnings': ['quiet'],
            'key_markers': 1,
        }
    ]


def test_session_browser_ignores_invalid_manifests(tmp_path: Path) -> None:
    manifest = tmp_path / 'recs-session.jsonl'
    manifest.write_text('{')

    assert session_browser.scan(tmp_path) == []
