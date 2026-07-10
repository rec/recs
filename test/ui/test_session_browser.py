import json
from pathlib import Path

from recs.ui import session_browser


def test_session_browser_lists_session_manifests(
    capsys,
    tmp_path: Path,
) -> None:
    manifest = tmp_path / 'take/recs-session.json'
    manifest.parent.mkdir()
    manifest.write_text(
        json.dumps(
            {
                'started_at': 'start',
                'ended_at': 'end',
                'duration': 1.5,
                'events': [{'timestamp': 'mark', 'type': 'key_pressed', 'key': 'g'}],
                'files': [
                    {
                        'path': 'take.wav',
                        'track': 1,
                        'channels': 1,
                        'sample_rate': 48000,
                        'bit_depth': 32,
                    }
                ],
                'warnings': ['quiet'],
            }
        )
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
    manifest = tmp_path / 'recs-session.json'
    manifest.write_text('{')

    assert session_browser.scan(tmp_path) == []
