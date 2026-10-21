import hashlib
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pytest
import soundfile
from pytest_regressions.data_regression import DataRegressionFixture
from ufor.time import ClockObservation, Position, Rate, Timebase

from recs.__main__ import run
from recs.base.errors import RecsError
from recs.recording.files import verify_recording
from recs.recording.finalize import finalize_recording
from recs.recording.offset import offset_sessions
from recs.recording.read import read_recording
from recs.recording.session_record import (
    AudioFileRecord,
    ClockRecord,
    EventRecord,
    MarkerPosition,
    SessionFooter,
    SessionRecordWriter,
    WarningRecord,
    read,
    read_entries,
)


def make_session(root: Path, start: str, continued_from: str | None = None) -> Path:
    timestamp = datetime.fromisoformat(start)
    session = root / '-default-' / timestamp.strftime('%Y/%m/%d/%H-%M-%S')
    audio = session / 'audio' / f'mic + {timestamp.strftime("%Y%m%d-%H%M%S")}.wav'
    audio.parent.mkdir(parents=True)
    soundfile.write(audio, np.zeros(48000), 48000, subtype='PCM_16')
    writer = SessionRecordWriter(
        session / 'session-record.jsonl',
        start,
        continued_from=continued_from,
        metadata={'timestamp': start, 'path': 'user data'},
    )
    writer.write(
        ClockRecord(
            timebases=[
                Timebase(name='wall', rate=Rate(numerator=1_000_000_000)),
                Timebase(name='capture', rate=Rate(numerator=48000)),
            ],
            observation=ClockObservation(
                source=Position(timebase='capture', tick=0),
                session=Position(timebase='wall', tick=100_000_000_000),
                timing_source='test',
            ),
        )
    )
    writer.write(
        AudioFileRecord(
            type='file_started',
            timestamp=start,
            stream_id='audio:mic:left',
            path=audio.relative_to(session).as_posix(),
            clock_id='capture',
            frame_count=0,
            source_channels=[1],
            sample_rate=48000,
        )
    )
    writer.write(
        AudioFileRecord(
            type='file_finished',
            quantity_count=48000,
            timestamp=start,
            stream_id='audio:mic:left',
            path=audio.relative_to(session).as_posix(),
            clock_id='capture',
            frame_count=48000,
            source_channels=[1],
            sample_rate=48000,
        )
    )
    writer.write(
        EventRecord(
            type='marker',
            timestamp=start,
            label='keep me',
            positions=[
                MarkerPosition(
                    source='mic',
                    clock_id='capture',
                    frame=48000,
                    sample_rate=48000,
                    observed_at=start,
                )
            ],
        )
    )
    writer.write(
        WarningRecord(timestamp=start, first_timestamp=start, message='keep warning')
    )
    writer.write(
        SessionFooter(
            ended_at=(timestamp + timedelta(seconds=1)).isoformat(), duration_seconds=1
        )
    )
    writer.close()
    finalize_recording(writer.path)
    return session


@pytest.mark.parametrize('seconds', [120, -120])
def test_offsets_wall_times_paths_and_hashes_without_changing_media(
    tmp_path: Path,
    seconds: int,
    data_regression: DataRegressionFixture,
) -> None:
    session = make_session(tmp_path, '2025-12-31T23:59:00Z')
    original = next(session.rglob('*.wav')).read_bytes()
    original_document = read_recording(session / 'recording.toml')

    result = offset_sessions(tmp_path, seconds)

    destination = result[0][1]
    assert not session.exists()
    assert next(destination.rglob('*.wav')).read_bytes() == original
    document = read_recording(destination / 'recording.toml')
    verification = verify_recording(document, destination)
    assert verification.audio_frames == 48000
    assert document.body.streams == original_document.body.streams
    record = read(destination / 'session-record.jsonl')
    entries, errors = read_entries(destination / 'session-record.jsonl')
    assert not errors
    observation = next(e for e in entries if isinstance(e, ClockRecord)).observation
    data_regression.check(
        {
            'directory': destination.relative_to(tmp_path).as_posix(),
            'media': next(destination.rglob('*.wav')).name,
            'record': record.model_dump(mode='json'),
            'document_start': document.body.started_at,
            'document_end': document.body.ended_at,
            'wall_tick': observation.session.tick,
            'source_tick': observation.source.tick,
        }
    )


def test_rebases_links_when_destinations_are_other_source_sessions(
    tmp_path: Path,
) -> None:
    first = make_session(tmp_path, '2025-12-31T23:59:00Z')
    second_start = tmp_path / '-default-/2026/01/01/00-00-00'
    relative = os.path.relpath(first / 'session-record.jsonl', second_start)
    second = make_session(tmp_path, '2026-01-01T00:00:00Z', relative)
    changes = dict(offset_sessions(tmp_path, 60))

    record = read(changes[second] / 'session-record.jsonl')
    assert record.continued_from is not None
    assert (changes[second] / record.continued_from).resolve() == changes[
        first
    ] / 'session-record.jsonl'
    document = read_recording(changes[second] / 'recording.toml')
    assert document.body.continued_from is not None
    assert (changes[second] / document.body.continued_from).resolve() == changes[
        first
    ] / 'recording.toml'
    verify_recording(document, changes[second])


def test_collision_leaves_all_sessions_unchanged(tmp_path: Path) -> None:
    first = make_session(tmp_path, '2025-12-31T23:59:00Z')
    make_session(tmp_path, '2026-01-02T00:00:00Z')
    occupied = tmp_path / '-default-/2026/01/02/00-01-00'
    occupied.mkdir()
    before = {
        p: hashlib.sha256(p.read_bytes()).hexdigest()
        for p in tmp_path.rglob('*')
        if p.is_file()
    }

    with pytest.raises(RecsError, match='Destination already exists'):
        offset_sessions(tmp_path, 60)

    assert first.exists()
    assert before == {
        p: hashlib.sha256(p.read_bytes()).hexdigest()
        for p in tmp_path.rglob('*')
        if p.is_file()
    }


def test_invalid_later_journal_leaves_earlier_sessions_unchanged(
    tmp_path: Path,
) -> None:
    first = make_session(tmp_path, '2025-12-31T23:59:00Z')
    second = make_session(tmp_path, '2026-01-01T00:00:00Z')
    journal = first / 'session-record.jsonl'
    original = journal.read_bytes()
    (second / 'session-record.jsonl').write_text('{broken\n')

    with pytest.raises(RecsError, match='truncated final line'):
        offset_sessions(tmp_path, 60)

    assert journal.read_bytes() == original


def test_offset_cli_accepts_negative_seconds_for_one_session(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    session = make_session(tmp_path, '2025-12-31T23:59:00Z')
    monkeypatch.setattr(sys, 'argv', ['recs', 'offset', str(session), '-3600'])
    assert run() == 0
    assert (session.parent / '22-59-00/recording.toml').exists()


def test_journal_only_session_and_unrelated_files(tmp_path: Path) -> None:
    session = tmp_path / '-default-/2026/01/01/00-00-00'
    session.mkdir(parents=True)
    (session / 'session-record.jsonl').write_text(
        json.dumps(
            {'type': 'header', 'version': 5, 'started_at': '2026-01-01T00:00:00Z'}
        )
        + '\n'
    )
    (session / 'notes.txt').write_text('unchanged')
    (tmp_path / 'unrelated.txt').write_text('also unchanged')

    destination = offset_sessions(tmp_path, -1)[0][1]

    assert (
        read(destination / 'session-record.jsonl').started_at == '2025-12-31T23:59:59Z'
    )
    assert (destination / 'notes.txt').read_text() == 'unchanged'
    assert (tmp_path / 'unrelated.txt').read_text() == 'also unchanged'


def test_io_failure_retains_original_media_and_journal(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = make_session(tmp_path, '2025-12-31T23:59:00Z')
    original_media = next(session.rglob('*.wav')).read_bytes()
    original_journal = (session / 'session-record.jsonl').read_bytes()
    rename = Path.rename

    def fail_media_move(self: Path, target: Path) -> Path:
        if self.suffix == '.wav':
            raise OSError('simulated storage failure')
        return rename(self, target)

    monkeypatch.setattr(Path, 'rename', fail_media_move)
    with pytest.raises(RecsError, match='retained files in'):
        offset_sessions(tmp_path, 60)

    staging = next(tmp_path.glob('recs-offset-*'))
    assert next(staging.rglob('*.wav')).read_bytes() == original_media
    assert next(staging.rglob('session-record.jsonl')).read_bytes() == original_journal


def test_named_session_and_native_event_payload_are_preserved(tmp_path: Path) -> None:
    session = make_session(tmp_path, '2025-12-31T23:59:00Z')
    named = session.with_name('take-one')
    session.rename(named)
    payload = named / 'midi' / 'keyboard-20251231-235900.jsonl'
    payload.parent.mkdir()
    payload.write_text('{"tick":123456,"ordinal":0,"data":[144,60,100]}\n')
    original = payload.read_bytes()

    assert offset_sessions(named, 60) == [(named, named)]

    assert (payload.parent / 'keyboard-20260101-000000.jsonl').read_bytes() == original
    verify_recording(read_recording(named / 'recording.toml'), named)
