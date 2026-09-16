import json
from hashlib import sha256
from pathlib import Path

import numpy as np
import pytest
import soundfile
from pytest_regressions.data_regression import DataRegressionFixture
from ufor.recording import AudioStream

from recs.base.errors import RecsError
from recs.recording import session_record, session_recovery
from recs.recording.files import verify_recording
from recs.recording.read import read_recording


@pytest.fixture
def interrupted(tmp_path: Path) -> Path:
    root = tmp_path / 'original'
    root.mkdir()
    audio = np.linspace(-0.5, 0.5, 48_000, dtype=np.float32)
    for name in ('complete.wav', 'unfinished.wav'):
        soundfile.write(root / name, audio, 48_000, subtype='FLOAT')
    writer = session_record.SessionRecordWriter(
        root / 'session-record.jsonl', started_at='start'
    )
    for name in ('complete.wav', 'unfinished.wav', 'missing.wav'):
        start = session_record.AudioFileRecord(
            type='file_started',
            timestamp='start',
            stream_id=f'audio:{name}',
            path=name,
            format='wav',
            clock_id='mic-clock',
            frame_count=12_000,
            source='Mic',
            channels=1,
            sample_rate=48_000,
        )
        writer.write(start)
        if name != 'unfinished.wav':
            writer.write(
                start.model_copy(
                    update={
                        'type': 'file_finished',
                        'frame_count': 60_000,
                        'quantity_count': 48_000,
                    }
                )
            )
    writer.close()
    with writer.path.open('a') as target:
        target.write('{"type":')
    return root


def test_recovery_plan_distinguishes_missing_and_unplaced_media(
    interrupted: Path, data_regression: DataRegressionFixture
) -> None:
    before = {p.name: p.read_bytes() for p in interrupted.iterdir()}
    first = session_recovery.inspect_recovery(interrupted)
    assert session_recovery.inspect_recovery(interrupted) == first
    assert {p.name: p.read_bytes() for p in interrupted.iterdir()} == before
    normalized = json.loads(
        first.model_dump_json().replace(str(interrupted), '<original>')
    )
    for item in normalized['files']:
        if item['asset'] is not None:
            assert item['asset']['sha256'] == sha256(before[item['path']]).hexdigest()
            item['asset']['sha256'] = '<verified file checksum>'
    data_regression.check(normalized)


def test_recovery_seals_verified_copy_and_preserves_evidence(
    interrupted: Path, tmp_path: Path
) -> None:
    before = {p.name: p.read_bytes() for p in interrupted.iterdir()}
    plan = session_recovery.inspect_recovery(interrupted)
    target = session_recovery.recover(plan, tmp_path / 'recovered')
    document = read_recording(target / 'recording.toml')
    assert document.body.state == 'sealed'
    assert document.body.unfinished_files == []
    assert document.body.continued_at == []
    assert len(document.body.streams) == 1
    stream = document.body.streams[0]
    assert isinstance(stream, AudioStream)
    assert stream.fragments[0].start == 12_000
    assert stream.fragments[0].count == 48_000
    assert (target / 'evidence/session-record.jsonl').read_bytes() == before[
        'session-record.jsonl'
    ]
    for item in plan.files:
        if item.recovered_path is not None:
            assert (target / item.recovered_path).read_bytes() == before[item.path]
    unplaced = next(
        f for f in plan.files if f.decision == session_recovery.Decision.unplaced
    )
    assert any(a.path == unplaced.recovered_path for a in document.assets)
    assert all(
        f.asset != unplaced.asset.name
        for s in document.body.streams
        for f in s.fragments
    )
    assert verify_recording(document, target).audio_frames == 48_000
    assert {p.name: p.read_bytes() for p in interrupted.iterdir()} == before


def test_failed_copy_retains_partial_work_without_publishing(
    interrupted: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plan = session_recovery.inspect_recovery(interrupted)
    before = {p.name: p.read_bytes() for p in interrupted.iterdir()}

    def fail(*args: object, **kwargs: object) -> None:
        raise OSError('disk disconnected')

    monkeypatch.setattr(session_recovery.shutil, 'copy2', fail)
    target = tmp_path / 'failed'
    with pytest.raises(RecsError, match='partial work retained'):
        session_recovery.recover(plan, target)
    assert not target.exists()
    assert len(list(tmp_path.glob('.failed.recs-recovery-*'))) == 1
    assert {p.name: p.read_bytes() for p in interrupted.iterdir()} == before


@pytest.mark.parametrize('name', ['session-record.jsonl', 'complete.wav'])
def test_changed_evidence_prevents_publication(
    interrupted: Path, tmp_path: Path, name: str
) -> None:
    plan = session_recovery.inspect_recovery(interrupted)
    with (interrupted / name).open('ab') as output:
        output.write(b'changed')
    target = tmp_path / 'changed'
    with pytest.raises(RecsError, match='changed'):
        session_recovery.recover(plan, target)
    assert not target.exists()


def test_recovery_refuses_interior_journal_corruption(interrupted: Path) -> None:
    path = interrupted / 'session-record.jsonl'
    path.write_text(path.read_text() + '\n{}\n')
    plan = session_recovery.inspect_recovery(interrupted)
    assert plan.failures
    assert not plan.files


def test_recovery_never_reuses_a_destination(interrupted: Path, tmp_path: Path) -> None:
    plan = session_recovery.inspect_recovery(interrupted)
    target = tmp_path / 'existing'
    target.mkdir()
    sentinel = target / 'keep'
    sentinel.write_text('keep')
    with pytest.raises(RecsError, match='already exists'):
        session_recovery.recover(plan, target)
    assert sentinel.read_text() == 'keep'
    with pytest.raises(RecsError, match='outside the original'):
        session_recovery.recover(plan, interrupted / 'nested')


def test_recovery_cli_preview_has_matching_text_and_json(
    interrupted: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert session_recovery.main([str(interrupted), '--json']) == 0
    report = json.loads(capsys.readouterr().out)
    assert session_recovery.main([str(interrupted)]) == 0
    text = capsys.readouterr().out
    for item in report['files']:
        assert f'{item["decision"]}: {item["path"]}: {item["reason"]}' in text
