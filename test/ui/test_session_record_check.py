from pathlib import Path

import pytest
from ufor.codec import score_toml
from ufor.recording import EventFragment, EventStream

from recs.recording.files import sealed_asset
from recs.recording.finalize import finalize_recording
from recs.recording.read import read_recording
from recs.ui import session_record, session_record_check


@pytest.fixture
def recording(tmp_path: Path) -> Path:
    writer = session_record.SessionRecordWriter(
        tmp_path / 'session-record.jsonl', started_at='start'
    )
    writer.write(session_record.SessionFooter(ended_at='end', duration_seconds=1))
    writer.close()
    return finalize_recording(writer.path)


def test_record_check_accepts_verified_recording(recording: Path) -> None:
    assert session_record_check.check(recording) == []


def test_record_check_detects_changed_journal(recording: Path) -> None:
    with recording.with_name('session-record.jsonl').open('a') as target:
        target.write('{}\n')
    assert 'Asset bytes disagree' in session_record_check.check(recording)[0]


def test_record_check_reports_missing_asset(recording: Path) -> None:
    journal = recording.with_name('session-record.jsonl')
    journal.rename(journal.with_name('moved.jsonl'))
    assert 'No such file' in session_record_check.check(recording)[0]


def test_record_check_reports_corrupt_midi_payload(recording: Path) -> None:
    path = recording.parent / 'bad.mid'
    path.write_bytes(b'MThd')
    document = read_recording(recording)
    value = document.model_copy(
        update={
            'assets': document.assets
            + [sealed_asset(path, path.parent, 'midi', 'smf')],
            'body': document.body.model_copy(
                update={
                    'streams': [
                        EventStream(
                            name='midi',
                            source_id='port',
                            event_schema='midi',
                            fragments=[
                                EventFragment(asset='midi', event_count=0, timing='smf')
                            ],
                        )
                    ]
                }
            ),
        }
    )
    recording.write_text(score_toml(value))
    errors = session_record_check.check(recording)
    assert len(errors) == 1
    assert 'EOFError' in errors[0]
    assert str(recording) in errors[0]


def test_record_check_reports_open_recording(recording: Path) -> None:
    document = read_recording(recording)
    value = document.model_copy(
        update={
            'body': document.body.model_copy(update={'state': 'open', 'ended_at': None})
        }
    )
    recording.write_text(score_toml(value))
    assert 'recording is open' in session_record_check.check(recording)[0]


def test_record_check_reports_broken_continuation(recording: Path) -> None:
    document = read_recording(recording)
    value = document.model_copy(
        update={
            'body': document.body.model_copy(
                update={'continued_at': ['missing/recording.toml']}
            )
        }
    )
    recording.write_text(score_toml(value))
    assert 'missing/recording.toml' in session_record_check.check(recording)[0]


@pytest.mark.parametrize(
    'value',
    [
        'not TOML',
        """
format = "unknown"
kind = "recording"
""",
    ],
)
def test_record_check_reports_invalid_document(recording: Path, value: str) -> None:
    recording.write_text(value)
    assert 'Cannot read recording' in session_record_check.check(recording)[0]
