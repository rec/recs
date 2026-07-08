import json
from pathlib import Path

from recs.ui.session_manifest import SessionManifest


def test_session_manifest_writes_atomically(tmp_path: Path) -> None:
    path = tmp_path / 'recs-session.json'
    manifest = SessionManifest(started_at='start', ended_at='end', duration=1.0)

    result = manifest.write(path)

    assert result == path
    assert json.loads(path.read_text()) == {
        'started_at': 'start',
        'ended_at': 'end',
        'duration': 1.0,
        'events': [],
        'files': [],
        'warnings': [],
    }
    assert not (tmp_path / '.recs-session.json.tmp').exists()
