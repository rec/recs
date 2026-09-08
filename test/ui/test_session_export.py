import hashlib
from pathlib import Path

import numpy as np
import pytest
import soundfile
import tomlkit
from ufor.arrangement import Arrangement, ArrangementDocument, SourceSpec
from ufor.references import RecordSelector
from ufor.time import Rate, Timebase

from recs.base.errors import RecsError
from recs.edit.materialized import materialize_source
from recs.edit.record import resolve_sources
from recs.recording.finalize import finalize_recording
from recs.recording.read import read_recording_chain
from recs.ui import session_export, session_record, session_record_check


def test_export_preserves_native_positions_and_remains_readable_after_source_moves(
    tmp_path: Path,
) -> None:
    originals = tmp_path / 'originals'
    first = _record(originals / 'a', 0, None, '../b/session-record.jsonl')
    second = _record(originals / 'b', 96000, '../a/session-record.jsonl', None)
    expected = {
        p.parent.name: hashlib.sha256((p.parent / 'take.wav').read_bytes()).hexdigest()
        for p in (first, second)
    }
    result = session_export.export(first, tmp_path / 'export')
    originals.rename(tmp_path / 'moved-originals')
    records = read_recording_chain(result / 'recording.toml')
    assert len(records) == 2
    for path, document in records:
        assert (
            hashlib.sha256((path.parent / 'take.wav').read_bytes()).hexdigest()
            == expected[document.name]
        )
    assert session_record_check.check(result / 'recording.toml') == []
    edit = ArrangementDocument(
        id='test',
        name='Test',
        timebases=[Timebase(id='audio', rate=Rate(numerator=48000))],
        body=Arrangement(
            timebase='audio',
            sources=[
                SourceSpec(
                    id='take',
                    record=result / 'recording.toml',
                    selector=RecordSelector(source='device', track='mono'),
                )
            ],
        ),
    )
    source = resolve_sources(edit, tmp_path)['take']
    assert [(f.start, f.end) for f in source.fragments] == [(0, 48000), (96000, 144000)]
    rendered = materialize_source(source)
    assert rendered.samples.shape == (144000, 1)
    soundfile.write(tmp_path / 'restored.wav', rendered.samples, 48000, subtype='FLOAT')
    actual, _ = soundfile.read(tmp_path / 'restored.wav')
    np.testing.assert_array_equal(actual[48000:96000], 0)
    summary = tomlkit.parse((result / 'export-summary.toml').read_text())
    assert summary['record_count'] == 2
    assert summary['file_count'] == 4


def test_export_rejects_changed_assets_before_writing(tmp_path: Path) -> None:
    record = _record(tmp_path / 'a', 0, None, None)
    with (record.parent / 'take.wav').open('ab') as target:
        target.write(b'changed')
    with pytest.raises(RecsError, match='Asset bytes disagree'):
        session_export.export(record, tmp_path / 'export')
    assert not (tmp_path / 'export').exists()
    assert not list(tmp_path.glob('.export.recs-export-*'))


def _record(
    directory: Path, start: int, previous: str | None, following: str | None
) -> Path:
    directory.mkdir(parents=True)
    tone = np.sin(np.arange(48000) * (2 * np.pi * 440 / 48000)) * 0.25
    soundfile.write(directory / 'take.wav', tone, 48000, subtype='FLOAT')
    writer = session_record.SessionRecordWriter(
        directory / 'session-record.jsonl',
        started_at='start',
        session_id=directory.name,
        continued_from=previous,
    )
    for kind in ('file_started', 'file_finished'):
        writer.write(
            session_record.AudioFileRecord(
                clock_id='audio',
                type=kind,
                media_type='audio',
                stream_id='audio:device:1',
                format='wav',
                timestamp='time',
                path='take.wav',
                source='device',
                track_name='mono',
                source_channels=[1],
                channels=1,
                sample_rate=48000,
                frame_count=start + (48000 if kind == 'file_finished' else 0),
                quantity_count=48000 if kind == 'file_finished' else None,
            )
        )
    if following:
        writer.write(
            session_record.EventRecord(
                type='session_continued_at', timestamp='time', continued_at=following
            )
        )
    writer.write(session_record.SessionFooter(ended_at='end', duration_seconds=1))
    writer.close()
    return finalize_recording(writer.path)
