import json
from pathlib import Path

from recs.ui import session_manifest_check


def test_manifest_check_accepts_existing_files(tmp_path: Path) -> None:
    audio = tmp_path / 'take.wav'
    audio.touch()
    manifest = tmp_path / 'recs-session.json'
    manifest.write_text(
        json.dumps(
            {
                'started_at': 'start',
                'ended_at': 'end',
                'duration': 1,
                'files': [
                    {
                        'path': 'take.wav',
                        'track': 1,
                        'channels': 1,
                        'sample_rate': 48_000,
                        'bit_depth': 32,
                    }
                ],
            }
        )
    )

    assert session_manifest_check.check(manifest) == []


def test_manifest_check_reports_missing_files(tmp_path: Path) -> None:
    manifest = tmp_path / 'recs-session.json'
    manifest.write_text(
        json.dumps(
            {
                'started_at': 'start',
                'ended_at': 'end',
                'duration': 1,
                'files': [
                    {
                        'path': 'missing.wav',
                        'track': 1,
                        'channels': 1,
                        'sample_rate': 48_000,
                        'bit_depth': 32,
                    }
                ],
            }
        )
    )

    assert session_manifest_check.check(manifest) == [
        f'{manifest}: missing file missing.wav'
    ]


def test_manifest_check_reports_unknown_fields(tmp_path: Path) -> None:
    manifest = tmp_path / 'recs-session.json'
    manifest.write_text(
        json.dumps(
            {
                'started_at': 'start',
                'ended_at': 'end',
                'duration': 1,
                'unknown': True,
            }
        )
    )

    assert 'Extra inputs are not permitted' in session_manifest_check.check(manifest)[0]
