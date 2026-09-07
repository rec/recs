import hashlib
import json
from pathlib import Path

import mido
import numpy as np
import pytest
import soundfile
from pytest_regressions.data_regression import DataRegressionFixture
from reccy.protocol.jsonl import Compress

from recs.base.errors import RecsError
from recs.model import recording
from recs.model.codec import parse_document
from recs.model.recording import AudioStream, RecordingDocument
from recs.recording import legacy
from recs.recording.files import sealed_asset, verify_recording
from recs.recording.legacy_finalize import prepare_legacy_recording
from recs.recording.migrate import migrate_session


@pytest.fixture
def session(tmp_path: Path) -> Path:
    root = tmp_path / 'session'
    root.mkdir()
    samples = np.sin(np.arange(48000) * (2 * np.pi * 440 / 48000)) * 0.25
    soundfile.write(root / 'audio.wav', samples, 48000, subtype='PCM_16')
    midi = mido.MidiFile()
    midi.tracks.append(
        mido.MidiTrack(
            [
                mido.MetaMessage('set_tempo', tempo=500000),
                mido.Message('note_on', note=60, velocity=100, time=0),
                mido.Message('note_off', note=60, time=480),
            ]
        )
    )
    midi.save(root / 'notes.mid')
    packets = list(
        Compress(key='kind')(
            [
                {
                    'kind': 'osc',
                    'monotonic': 1.0,
                    'direction': 'in',
                    'data_b64': 'L3gAAA==',
                },
                {
                    'kind': 'osc',
                    'monotonic': 2.0,
                    'direction': 'in',
                    'data_b64': 'L3gAAA==',
                },
            ]
        )
    )
    for index, packet in enumerate(packets):
        (root / f'osc-{index}.jsonl').write_text(json.dumps(packet) + '\n')
    records: list[legacy.Record] = [
        legacy.SessionHeader(
            started_at='2026-09-04T12:00:00Z', session_id='test-session'
        )
    ]
    for media, encoding, path, start, count in (
        ('audio', 'wav', 'audio.wav', 48000, 48000),
        ('midi', 'smf', 'notes.mid', None, 2),
        ('osc', 'jsonl', 'osc-0.jsonl', None, 1),
        ('osc', 'jsonl', 'osc-1.jsonl', None, 1),
    ):
        for kind in ('file_started', 'file_finished'):
            records.append(
                legacy.FileRecord(
                    type=kind,
                    media_type=media,
                    format=encoding,
                    path=path,
                    stream_id=f'{media}:desk',
                    timestamp='2026-09-04T12:00:01Z',
                    frame_count=None
                    if start is None
                    else start + (count if kind == 'file_finished' else 0),
                    quantity_count=count if kind == 'file_finished' else None,
                    sample_rate=48000 if media == 'audio' else None,
                    channels=1 if media == 'audio' else None,
                )
            )
    records.append(
        legacy.SessionFooter(ended_at='2026-09-04T12:00:03Z', duration_seconds=3)
    )
    (root / 'session-record.jsonl').write_text(
        ''.join(r.model_dump_json(exclude_none=True) + '\n' for r in records)
    )
    return root


def test_migration_preserves_payloads_and_native_gap_positions(
    session: Path,
    data_regression: DataRegressionFixture,
) -> None:
    before = {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in session.iterdir()
    }
    path, report = migrate_session(session)
    document = parse_document(path.read_text())
    assert isinstance(document, RecordingDocument)
    data_regression.check(document.model_dump(mode='json'))
    assert report.audio_frames == 48000
    assert report.event_count == 4
    assert report.gap_frames == 48000
    assert verify_recording(document, session).audio_frames == 48000
    assert all(
        hashlib.sha256((session / n).read_bytes()).hexdigest() == h
        for n, h in before.items()
    )
    assert (session / 'migration/session-record-v3.jsonl').read_bytes() == (
        session / 'session-record.jsonl'
    ).read_bytes()
    assert legacy.read(session / 'session-record.jsonl').duration_seconds == 3
    with pytest.raises(RecsError, match='already exists'):
        migrate_session(session)


def test_changed_media_fails_verification(session: Path) -> None:
    document, _ = prepare_legacy_recording(session / 'session-record.jsonl')
    with (session / 'audio.wav').open('ab') as output:
        output.write(b'changed')
    with pytest.raises(RecsError, match='Asset bytes disagree'):
        verify_recording(document, session)


def test_frame_count_mismatch_preserves_audio_without_inventing_placement(
    session: Path,
) -> None:
    samples, rate = soundfile.read(session / 'audio.wav')
    soundfile.write(
        session / 'audio.wav',
        np.concatenate([samples, samples]),
        rate,
        subtype='PCM_16',
    )
    path, report = migrate_session(session)
    document = parse_document(path.read_text())
    assert isinstance(document, RecordingDocument)
    stream = document.body.streams[0]
    assert isinstance(stream, AudioStream)
    assert stream.fragments == []
    assert stream.unmapped_fragments[0].count == 96000
    assert stream.unmapped_fragments[0].journal_range.end == 96000
    assert stream.unmapped_fragments[0].journal_range.start == 48000
    assert report.unresolved_audio_files == 1
    assert report.audio_frames == 96000
    assert any('timeline placement is unresolved' in n for n in report.notes)


def test_explicit_path_base_handles_historical_session_prefix(session: Path) -> None:
    path = session / 'session-record.jsonl'
    entries, _ = legacy.read_entries(path)
    entries = [
        e.model_copy(update={'path': 'session/' + e.path})
        if isinstance(e, legacy.FileRecord)
        else e
        for e in entries
    ]
    path.write_text(
        ''.join(e.model_dump_json(exclude_none=True) + '\n' for e in entries)
    )
    document, _ = prepare_legacy_recording(path, session.parent)
    audio = document.body.streams[0]
    assert isinstance(audio, AudioStream)
    assert audio.fragments[0].start == 48000
    assert verify_recording(document, session).audio_frames == 48000
    assert all(not a.path.startswith('session/') for a in document.assets)


def test_unfinished_files_and_torn_tail_remain_visibly_open(session: Path) -> None:
    path = session / 'session-record.jsonl'
    entries, _ = legacy.read_entries(path)
    entries.insert(
        -1,
        legacy.FileRecord(
            type='file_started',
            media_type='audio',
            format='wav',
            path='incomplete.wav',
            stream_id='audio:unfinished',
            timestamp='2026-09-04T12:00:02Z',
        ),
    )
    path.write_text(
        ''.join(e.model_dump_json(exclude_none=True) + '\n' for e in entries)
    )
    document, _ = prepare_legacy_recording(path)
    assert document.body.state == 'open'
    assert document.body.unfinished_files[0].journal_path == 'incomplete.wav'
    with path.open('a') as output:
        output.write('{"type":')
    output_path, report = migrate_session(session)
    restored = parse_document(output_path.read_text())
    assert isinstance(restored, RecordingDocument)
    assert restored.body.state == 'open'
    assert any('truncated final line' in n for n in report.notes)


@pytest.mark.parametrize('bad_line', ['{"type": "footer"}\n', '{"type":\n{}\n'])
def test_invalid_complete_record_or_middle_line_is_an_error(
    session: Path, bad_line: str
) -> None:
    path = session / 'session-record.jsonl'
    with path.open('a') as output:
        output.write(bad_line)
    with pytest.raises(RecsError):
        migrate_session(session)
    assert not (session / 'recording.toml').exists()


def test_symlink_outside_session_is_rejected(session: Path) -> None:
    original = session / 'audio.wav'
    outside = session.parent / 'external.wav'
    original.rename(outside)
    original.symlink_to(outside)
    with pytest.raises(RecsError, match='escapes'):
        migrate_session(session)


def test_native_event_order_is_checked_across_fragments(session: Path) -> None:
    document, _ = prepare_legacy_recording(session / 'session-record.jsonl')
    for index in range(2):
        (session / f'events-{index}.jsonl').write_text(
            json.dumps(
                {
                    'kind': 'key',
                    'key': 'a',
                    'action': 'press',
                    'tick': 48000,
                    'ordinal': index,
                }
            )
            + '\n'
        )
    assets = [
        sealed_asset(
            session / f'events-{i}.jsonl', session, f'events-{i}', 'recs_events'
        )
        for i in range(2)
    ]
    stream = recording.EventStream(
        id='keys',
        source_id='keyboard',
        event_schema='recs_events',
        timebase=document.timebases[0].id,
        fragments=[
            recording.EventFragment(
                asset=a.id, timing='recs_events', event_count=1, start=48000, end=48001
            )
            for a in assets
        ],
    )
    candidate = document.model_copy(
        update={
            'assets': document.assets + assets,
            'body': document.body.model_copy(update={'streams': [stream]}),
        }
    )
    assert verify_recording(candidate, session).event_count == 2
    reversed_stream = stream.model_copy(
        update={'fragments': list(reversed(stream.fragments))}
    )
    reversed_document = candidate.model_copy(
        update={
            'body': candidate.body.model_copy(update={'streams': [reversed_stream]})
        }
    )
    with pytest.raises(RecsError, match='out of order'):
        verify_recording(reversed_document, session)
