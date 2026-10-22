import hashlib
import json
from pathlib import Path

import numpy as np
import pytest
import soundfile
from pytest_regressions.data_regression import DataRegressionFixture
from ufor.encoding import Format, Subtype
from ufor.recording import AudioStream
from ufor.references import RecordSelector

from recs.audio.playback import PlaybackTimeline
from recs.edit.commands import complete_or_generate
from recs.edit.inputs import SourceSpec
from recs.edit.options import EditOptions
from recs.edit.record import resolve_input
from recs.edit.session import execute_edit
from recs.recording import session_browser, session_record
from recs.recording.files import asset_path
from recs.recording.finalize import finalize_recording
from recs.recording.read import read_recording, read_recording_chain


def make_session(
    directory: Path,
    start_frame: int = 0,
    continued_from: str | None = None,
    continued_at: str | None = None,
) -> Path:
    directory.mkdir()
    audio = np.linspace(-0.5, 0.5, 48000, dtype=np.float32)
    soundfile.write(directory / 'take.wav', audio, 48000, subtype='FLOAT')
    writer = session_record.SessionRecordWriter(
        directory / 'session-record.jsonl',
        started_at='2026-10-22T12:00:00Z',
        session_id=directory.name,
        continued_from=continued_from,
    )
    values = {
        'stream_id': 'audio:Mic:voice',
        'clock_id': 'capture',
        'path': 'take.wav',
        'format': 'wav',
        'source': 'Mic',
        'track_name': 'voice',
        'sample_rate': 48000,
        'channels': 1,
        'source_channels': [1],
        'timestamp': '2026-10-22T12:00:00Z',
    }
    writer.write(
        session_record.AudioFileRecord(
            type='file_started', frame_count=start_frame, **values
        )
    )
    writer.write(
        session_record.AudioFileRecord(
            type='file_finished',
            frame_count=start_frame + 48000,
            quantity_count=48000,
            **values,
        )
    )
    if continued_at is not None:
        writer.write(
            session_record.EventRecord(
                type='session_continued_at',
                timestamp='2026-10-22T12:00:01Z',
                continued_at=continued_at,
            )
        )
    writer.write(
        session_record.SessionFooter(
            ended_at='2026-10-22T12:00:01Z', duration_seconds=1
        )
    )
    writer.close()
    return writer.path


def forbid_hashing(*args: object, **kwargs: object) -> object:
    raise AssertionError('Normal recording use must not hash recorded files')


@pytest.mark.parametrize('finalized', [False, True])
def test_browsing_reads_only_journal_metadata(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    finalized: bool,
) -> None:
    journal = make_session(tmp_path / 'session')
    if finalized:
        finalize_recording(journal)
    original_stat = Path.stat

    def metadata_stat(self: Path, *args: object, **kwargs: object) -> object:
        if self.suffix == '.wav':
            raise AssertionError('Browsing inspected recorded media')
        return original_stat(self, *args, **kwargs)

    monkeypatch.setattr(Path, 'stat', metadata_stat)
    monkeypatch.setattr(soundfile, 'info', forbid_hashing)
    monkeypatch.setattr(hashlib, 'file_digest', forbid_hashing)

    assert session_browser.main([str(tmp_path), '--json']) == 0
    summary = json.loads(capsys.readouterr().out)[0]
    assert summary['audio_files'] == 1
    assert summary['state'] == 'sealed'
    assert (summary['total_bytes'] is None) == (not finalized)
    assert journal.with_name('recording.toml').exists() == finalized
    assert session_browser.show([str(journal.parent)]) == 0


def test_playback_reads_a_session_without_an_index(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    data_regression: DataRegressionFixture,
) -> None:
    journal = make_session(tmp_path / 'session')
    monkeypatch.setattr(hashlib, 'file_digest', forbid_hashing)
    document = read_recording(journal.parent)
    stream = document.body.streams[0]
    assert isinstance(stream, AudioStream)
    timeline = PlaybackTimeline(journal.parent, document, stream)
    audio = timeline.read(0, 48000)
    timeline.close()
    soundfile.write(tmp_path / 'played.wav', audio, 48000, subtype='FLOAT')
    expected, rate = soundfile.read(
        journal.parent / 'take.wav', dtype='float32', always_2d=True
    )
    np.testing.assert_array_equal(audio, expected)
    data_regression.check(
        {
            'frames': len(audio),
            'channels': audio.shape[1],
            'rate': rate,
            'samples': hashlib.sha256(audio.tobytes()).hexdigest(),
        }
    )
    assert not journal.with_name('recording.toml').exists()


@pytest.mark.parametrize('input_kind', ['journal', 'index', 'file'])
def test_editing_never_hashes_input_or_output_audio(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, input_kind: str
) -> None:
    journal = make_session(tmp_path / 'session')
    finalized = input_kind == 'index'
    if finalized:
        finalize_recording(journal)
    monkeypatch.setattr(hashlib, 'file_digest', forbid_hashing)
    monkeypatch.chdir(tmp_path)
    edit = complete_or_generate(
        {'_command': {'operation': 'clip'}},
        [journal.parent / 'take.wav' if input_kind == 'file' else journal.parent],
        EditOptions(format=Format.wav, subtype=Subtype.float),
    )
    destination = tmp_path / 'edited'
    record = execute_edit(edit, tmp_path, destination)
    document = read_recording(record)
    asset = next(a for a in document.assets if a.encoding == 'wav')
    actual, rate = soundfile.read(destination / asset_path(asset), dtype='float32')
    expected, _ = soundfile.read(journal.parent / 'take.wav', dtype='float32')
    np.testing.assert_array_equal(actual, expected)
    assert rate == 48000
    assert all(
        a.content is not None and a.content.sha256 is None for a in document.assets
    )
    assert journal.with_name('recording.toml').exists() == finalized


def test_continuation_links_work_without_indexes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    first = make_session(
        tmp_path / 'first', continued_at='../second/session-record.jsonl'
    )
    second = make_session(
        tmp_path / 'second', 48000, continued_from='../first/session-record.jsonl'
    )
    monkeypatch.setattr(hashlib, 'file_digest', forbid_hashing)

    chain = read_recording_chain(first.with_name('recording.toml'))
    assert {p for p, _ in chain} == {first, second}
    source = resolve_input(
        SourceSpec(
            name='voice',
            record=first,
            selector=RecordSelector(source='Mic', track='voice'),
        ),
        tmp_path,
    )
    assert [(f.start, f.end) for f in source.fragments] == [(0, 48000), (48000, 96000)]
    assert not first.with_name('recording.toml').exists()
    assert not second.with_name('recording.toml').exists()
