from pathlib import Path

from recs.ui import session_record_check


def test_record_check_accepts_existing_finished_files(tmp_path: Path) -> None:
    audio = tmp_path / 'take.wav'
    audio.touch()
    record = tmp_path / 'session-record.jsonl'
    record.write_text(
        '{"type":"header","version":3,"started_at":"start"}\n'
        '{"type":"file_started","media_type":"audio","stream_id":"audio:test:1","format":"wav","timestamp":"start","path":"take.wav",'
        '"track":1,"channels":1,"sample_rate":48000,"bit_depth":32}\n'
        '{"type":"file_finished","media_type":"audio","stream_id":"audio:test:1","format":"wav","timestamp":"end","path":"take.wav",'
        '"track":1,"channels":1,"sample_rate":48000,"bit_depth":32}\n'
        '{"type":"footer","ended_at":"end","duration_seconds":1}\n'
    )

    assert session_record_check.check(record) == []


def test_record_check_reports_missing_files(tmp_path: Path) -> None:
    record = tmp_path / 'session-record.jsonl'
    record.write_text(
        '{"type":"header","version":3,"started_at":"start"}\n'
        '{"type":"file_finished","media_type":"audio","stream_id":"audio:test:1","format":"wav","timestamp":"end","path":"missing.wav",'
        '"track":1,"channels":1,"sample_rate":48000,"bit_depth":32}\n'
        '{"type":"footer","ended_at":"end","duration_seconds":1}\n'
    )

    assert session_record_check.check(record) == [f'{record}: missing file missing.wav']


def test_record_check_rejects_absolute_file_paths(tmp_path: Path) -> None:
    audio = tmp_path / 'take.wav'
    audio.touch()
    record = tmp_path / 'session-record.jsonl'
    record.write_text(
        '{"type":"header","version":3,"started_at":"start"}\n'
        f'{{"type":"file_finished","media_type":"audio","stream_id":"audio:test:1","format":"wav","timestamp":"end","path":"{audio}"}}\n'
        '{"type":"footer","ended_at":"end","duration_seconds":1}\n'
    )

    assert session_record_check.check(record) == [
        f'{record}: file path must be relative: {audio}'
    ]


def test_record_check_rejects_file_paths_outside_session(tmp_path: Path) -> None:
    outside = tmp_path / 'outside.wav'
    outside.touch()
    session = tmp_path / 'session'
    session.mkdir()
    record = session / 'session-record.jsonl'
    record.write_text(
        '{"type":"header","version":3,"started_at":"start"}\n'
        '{"type":"file_finished","media_type":"audio",'
        '"stream_id":"audio:test:1","format":"wav","timestamp":"end",'
        '"path":"../outside.wav"}\n'
        '{"type":"footer","ended_at":"end","duration_seconds":1}\n'
    )

    assert session_record_check.check(record) == [
        f'{record}: file path escapes session: ../outside.wav'
    ]


def test_record_check_rejects_absolute_continuation_paths(tmp_path: Path) -> None:
    record = tmp_path / 'session-record.jsonl'
    record.write_text(
        '{"type":"header","version":3,"started_at":"start",'
        '"continued_from":"/outside/session-record.jsonl"}\n'
        '{"type":"footer","ended_at":"end","duration_seconds":1}\n'
    )

    assert session_record_check.check(record) == [
        f'{record}: continued_from must be relative'
    ]


def test_record_check_reports_unknown_fields(tmp_path: Path) -> None:
    record = tmp_path / 'session-record.jsonl'
    record.write_text(
        '{"type":"header","version":3,"started_at":"start","unknown":true}\n'
    )

    errors = session_record_check.check(record)
    assert any('Extra inputs are not permitted' in e for e in errors)


def test_record_check_reports_unfinished_files(tmp_path: Path) -> None:
    audio = tmp_path / 'take.wav'
    audio.touch()
    record = tmp_path / 'session-record.jsonl'
    record.write_text(
        '{"type":"header","version":3,"started_at":"start"}\n'
        '{"type":"file_started","media_type":"audio","stream_id":"audio:test:1","format":"wav","timestamp":"start","path":"take.wav",'
        '"track":1,"channels":1,"sample_rate":48000,"bit_depth":32}\n'
    )

    assert session_record_check.check(record) == [
        f'{record}: missing footer',
        f'{record}: unfinished file {audio.as_posix()}',
    ]


def test_record_check_reports_file_that_finishes_before_it_starts(
    tmp_path: Path,
) -> None:
    audio = tmp_path / 'take.wav'
    audio.write_bytes(b'0' * 100)
    record = tmp_path / 'session-record.jsonl'
    record.write_text(
        '{"type":"header","version":3,"started_at":"start"}\n'
        '{"type":"file_started","media_type":"audio","stream_id":"audio:test:1","format":"wav","timestamp":"start","path":"take.wav",'
        '"track":1,"channels":1,"sample_rate":48000,"bit_depth":32,'
        '"frame_count":100}\n'
        '{"type":"file_finished","media_type":"audio","stream_id":"audio:test:1","format":"wav","timestamp":"end","path":"take.wav",'
        '"track":1,"channels":1,"sample_rate":48000,"bit_depth":32,'
        '"frame_count":50}\n'
        '{"type":"footer","ended_at":"end","duration_seconds":1}\n'
    )

    assert session_record_check.check(record) == [
        f'{record}: take.wav finishes before it starts'
    ]


def test_record_check_reports_nonmonotonic_track_frames(tmp_path: Path) -> None:
    first = tmp_path / 'first.wav'
    second = tmp_path / 'second.wav'
    first.touch()
    second.touch()
    record = tmp_path / 'session-record.jsonl'
    record.write_text(
        '{"type":"header","version":3,"started_at":"start"}\n'
        '{"type":"file_finished","media_type":"audio","stream_id":"audio:test:1","format":"wav","timestamp":"a","path":"first.wav",'
        '"source":"Mic","track":1,"channels":1,"sample_rate":48000,'
        '"bit_depth":32,"frame_count":200}\n'
        '{"type":"file_finished","media_type":"audio","stream_id":"audio:test:1","format":"wav","timestamp":"b","path":"second.wav",'
        '"source":"Mic","track":1,"channels":1,"sample_rate":48000,'
        '"bit_depth":32,"frame_count":100}\n'
        '{"type":"footer","ended_at":"end","duration_seconds":1}\n'
    )

    assert session_record_check.check(record) == [
        f'{record}: frame count moved backwards for Mic track 1'
    ]


def test_record_check_reports_implausibly_small_file(tmp_path: Path) -> None:
    audio = tmp_path / 'take.wav'
    audio.write_bytes(b'0' * 10)
    record = tmp_path / 'session-record.jsonl'
    record.write_text(
        '{"type":"header","version":3,"started_at":"start"}\n'
        '{"type":"file_started","media_type":"audio","stream_id":"audio:test:1","format":"wav","timestamp":"start","path":"take.wav",'
        '"track":1,"channels":2,"sample_rate":48000,"bit_depth":32,'
        '"frame_count":0}\n'
        '{"type":"file_finished","media_type":"audio","stream_id":"audio:test:1","format":"wav","timestamp":"end","path":"take.wav",'
        '"track":1,"channels":2,"sample_rate":48000,"bit_depth":32,'
        '"frame_count":48000}\n'
        '{"type":"footer","ended_at":"end","duration_seconds":1}\n'
    )

    assert session_record_check.check(record) == [
        f'{record}: take.wav is smaller than 48000 frames at 2 channels/32 bits'
    ]


def test_record_check_reports_empty_midi_file_with_messages(tmp_path: Path) -> None:
    midi = tmp_path / 'keys.mid'
    midi.touch()
    record = tmp_path / 'session-record.jsonl'
    record.write_text(
        '{"type":"header","version":3,"started_at":"start"}\n'
        '{"type":"file_finished","media_type":"midi","stream_id":"midi:test","format":"smf","timestamp":"end",'
        '"path":"keys.mid","quantity_count":3,"midi_port":"Launchkey"}\n'
        '{"type":"footer","ended_at":"end","duration_seconds":1}\n'
    )

    assert session_record_check.check(record) == [
        f'{record}: keys.mid has MIDI messages but is empty'
    ]


def test_record_check_reports_broken_disk_switch_link(tmp_path: Path) -> None:
    continued = tmp_path / 'next.jsonl'
    continued.write_text(
        '{"type":"header","version":3,"started_at":"later",'
        '"continued_from":"wrong.jsonl"}\n'
        '{"type":"footer","ended_at":"end","duration_seconds":1}\n'
    )
    record = tmp_path / 'session-record.jsonl'
    record.write_text(
        '{"type":"header","version":3,"started_at":"start"}\n'
        '{"type":"disk_switch_continued_at","timestamp":"switch",'
        '"continued_at":"next.jsonl"}\n'
        '{"type":"footer","ended_at":"end","duration_seconds":1}\n'
    )

    assert session_record_check.check(record) == [
        f'{continued}: continued_from does not point back'
    ]
