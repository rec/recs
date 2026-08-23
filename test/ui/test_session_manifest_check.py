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


def test_manifest_check_rejects_absolute_file_paths(tmp_path: Path) -> None:
    audio = tmp_path / 'take.wav'
    audio.touch()
    manifest = tmp_path / 'audio-session.jsonl'
    manifest.write_text(
        '{"type":"header","version":2,"started_at":"start"}\n'
        f'{{"type":"file_finished","timestamp":"end","path":"{audio}"}}\n'
        '{"type":"footer","ended_at":"end","duration":1}\n'
    )

    assert session_manifest_check.check(manifest) == [
        f'{manifest}: file path must be relative: {audio}'
    ]


def test_manifest_check_rejects_absolute_continuation_paths(tmp_path: Path) -> None:
    manifest = tmp_path / 'audio-session.jsonl'
    manifest.write_text(
        '{"type":"header","version":2,"started_at":"start",'
        '"continued_from":"/outside/audio-session.jsonl"}\n'
        '{"type":"footer","ended_at":"end","duration":1}\n'
    )

    assert session_manifest_check.check(manifest) == [
        f'{manifest}: continued_from must be relative'
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


def test_manifest_check_reports_file_that_finishes_before_it_starts(
    tmp_path: Path,
) -> None:
    audio = tmp_path / 'take.wav'
    audio.write_bytes(b'0' * 100)
    manifest = tmp_path / 'recs-session.jsonl'
    manifest.write_text(
        '{"type":"header","version":2,"started_at":"start"}\n'
        '{"type":"file_started","timestamp":"start","path":"take.wav",'
        '"track":1,"channels":1,"sample_rate":48000,"bit_depth":32,'
        '"frame_count":100}\n'
        '{"type":"file_finished","timestamp":"end","path":"take.wav",'
        '"track":1,"channels":1,"sample_rate":48000,"bit_depth":32,'
        '"frame_count":50}\n'
        '{"type":"footer","ended_at":"end","duration":1}\n'
    )

    assert session_manifest_check.check(manifest) == [
        f'{manifest}: take.wav finishes before it starts'
    ]


def test_manifest_check_reports_nonmonotonic_track_frames(tmp_path: Path) -> None:
    first = tmp_path / 'first.wav'
    second = tmp_path / 'second.wav'
    first.touch()
    second.touch()
    manifest = tmp_path / 'recs-session.jsonl'
    manifest.write_text(
        '{"type":"header","version":2,"started_at":"start"}\n'
        '{"type":"file_finished","timestamp":"a","path":"first.wav",'
        '"source":"Mic","track":1,"channels":1,"sample_rate":48000,'
        '"bit_depth":32,"frame_count":200}\n'
        '{"type":"file_finished","timestamp":"b","path":"second.wav",'
        '"source":"Mic","track":1,"channels":1,"sample_rate":48000,'
        '"bit_depth":32,"frame_count":100}\n'
        '{"type":"footer","ended_at":"end","duration":1}\n'
    )

    assert session_manifest_check.check(manifest) == [
        f'{manifest}: frame count moved backwards for Mic track 1'
    ]


def test_manifest_check_reports_implausibly_small_file(tmp_path: Path) -> None:
    audio = tmp_path / 'take.wav'
    audio.write_bytes(b'0' * 10)
    manifest = tmp_path / 'recs-session.jsonl'
    manifest.write_text(
        '{"type":"header","version":2,"started_at":"start"}\n'
        '{"type":"file_started","timestamp":"start","path":"take.wav",'
        '"track":1,"channels":2,"sample_rate":48000,"bit_depth":32,'
        '"frame_count":0}\n'
        '{"type":"file_finished","timestamp":"end","path":"take.wav",'
        '"track":1,"channels":2,"sample_rate":48000,"bit_depth":32,'
        '"frame_count":48000}\n'
        '{"type":"footer","ended_at":"end","duration":1}\n'
    )

    assert session_manifest_check.check(manifest) == [
        f'{manifest}: take.wav is smaller than 48000 frames at 2 channels/32 bits'
    ]


def test_manifest_check_reports_empty_midi_file_with_messages(tmp_path: Path) -> None:
    midi = tmp_path / 'keys.mid'
    midi.touch()
    manifest = tmp_path / 'recs-session.jsonl'
    manifest.write_text(
        '{"type":"header","version":2,"started_at":"start"}\n'
        '{"type":"file_finished","kind":"midi","timestamp":"end",'
        '"path":"keys.mid","message_count":3,"midi_port":"Launchkey"}\n'
        '{"type":"footer","ended_at":"end","duration":1}\n'
    )

    assert session_manifest_check.check(manifest) == [
        f'{manifest}: keys.mid has MIDI messages but is empty'
    ]


def test_manifest_check_reports_broken_disk_switch_link(tmp_path: Path) -> None:
    continued = tmp_path / 'next.jsonl'
    continued.write_text(
        '{"type":"header","version":2,"started_at":"later",'
        '"continued_from":"wrong.jsonl"}\n'
        '{"type":"footer","ended_at":"end","duration":1}\n'
    )
    manifest = tmp_path / 'recs-session.jsonl'
    manifest.write_text(
        '{"type":"header","version":2,"started_at":"start"}\n'
        '{"type":"disk_switch_continued_at","timestamp":"switch",'
        '"continued_at":"next.jsonl"}\n'
        '{"type":"footer","ended_at":"end","duration":1}\n'
    )

    assert session_manifest_check.check(manifest) == [
        f'{continued}: continued_from does not point back'
    ]
