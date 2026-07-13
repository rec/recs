from pathlib import Path

from recs.ui import session_manifest_check


def test_manifest_check_accepts_existing_finished_files(tmp_path: Path) -> None:
    audio = tmp_path / 'take.wav'
    audio.touch()
    manifest = tmp_path / 'recs-session.jsonl'
    manifest.write_text(
        '{"type":"header","version":2,"started_at":"start"}\n'
        '{"type":"file_started","timestamp":"start","path":"take.wav",'
        '"track":1,"channels":1,"sample_rate":48000,"bit_depth":32}\n'
        '{"type":"file_finished","timestamp":"end","path":"take.wav",'
        '"track":1,"channels":1,"sample_rate":48000,"bit_depth":32}\n'
        '{"type":"footer","ended_at":"end","duration":1}\n'
    )

    assert session_manifest_check.check(manifest) == []


def test_manifest_check_reports_missing_files(tmp_path: Path) -> None:
    manifest = tmp_path / 'recs-session.jsonl'
    manifest.write_text(
        '{"type":"header","version":2,"started_at":"start"}\n'
        '{"type":"file_finished","timestamp":"end","path":"missing.wav",'
        '"track":1,"channels":1,"sample_rate":48000,"bit_depth":32}\n'
        '{"type":"footer","ended_at":"end","duration":1}\n'
    )

    assert session_manifest_check.check(manifest) == [
        f'{manifest}: missing file missing.wav'
    ]


def test_manifest_check_reports_unknown_fields(tmp_path: Path) -> None:
    manifest = tmp_path / 'recs-session.jsonl'
    manifest.write_text(
        '{"type":"header","version":2,"started_at":"start","unknown":true}\n'
    )

    errors = session_manifest_check.check(manifest)
    assert any('Extra inputs are not permitted' in e for e in errors)


def test_manifest_check_reports_unfinished_files(tmp_path: Path) -> None:
    audio = tmp_path / 'take.wav'
    audio.touch()
    manifest = tmp_path / 'recs-session.jsonl'
    manifest.write_text(
        '{"type":"header","version":2,"started_at":"start"}\n'
        '{"type":"file_started","timestamp":"start","path":"take.wav",'
        '"track":1,"channels":1,"sample_rate":48000,"bit_depth":32}\n'
    )

    assert session_manifest_check.check(manifest) == [
        f'{manifest}: missing footer',
        f'{manifest}: unfinished file {audio.as_posix()}',
    ]
