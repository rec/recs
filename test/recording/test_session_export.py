import hashlib
import json
from pathlib import Path

import numpy as np
import pytest
import soundfile
import tomlkit
from reccy.runtime.assets import AssetCategory, SourceKind, source_fingerprint
from ufor.assets import DownloadLocation, RelativeFileLocation
from ufor.codec import score_toml
from ufor.references import RecordSelector

from recs.base.errors import RecsError
from recs.edit.inputs import SourceSpec
from recs.edit.materialized import materialize_source
from recs.edit.record import resolve_input
from recs.recording import session_export, session_record, session_record_check
from recs.recording.finalize import finalize_recording
from recs.recording.read import read_recording, read_recording_chain


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
    edit = SourceSpec(
        name='take',
        record=result / 'recording.toml',
        selector=RecordSelector(source='device', track='mono'),
    )
    source = resolve_input(edit, tmp_path)
    assert [(f.start, f.end) for f in source.fragments] == [(0, 48000), (96000, 144000)]
    rendered = materialize_source(source)
    assert rendered.end_frame == 144000
    assert rendered.channels == 1
    with soundfile.SoundFile(
        tmp_path / 'restored.wav',
        'w',
        samplerate=48000,
        channels=rendered.channels,
        subtype='FLOAT',
    ) as fp:
        for block in rendered.blocks():
            fp.write(block)
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


def test_export_uses_cached_https_asset_and_seals_relative_package(
    tmp_path: Path,
) -> None:
    record = _record(tmp_path / 'source', 0, None, None)
    original = (record.parent / 'take.wav').read_bytes()
    document = read_recording(record)
    audio_asset_name = document.body.streams[0].fragments[0].asset
    url = 'https://example.test/take.wav'
    document = document.model_copy(
        update={
            'assets': [
                a.model_copy(update={'location': DownloadLocation(url=url)})
                if a.name == audio_asset_name
                else a
                for a in document.assets
            ]
        }
    )
    record.write_text(score_toml(document))
    (record.parent / 'take.wav').write_bytes(b'local copy is unavailable')
    policy = tmp_path / 'assets.toml'
    policy.write_text(
        f'cache_root = "{tmp_path / "cache"}"\n'
        'credential_scope = "export-test"\n'
        'maximum_bytes = 1000000\n'
        'timeout = 2\n'
        f'approved_https_urls = ["{url}"]\n'
    )
    resolver = session_export.load_asset_policy(policy)
    resolver.store.import_bytes(
        original,
        source_key=source_fingerprint({'kind': 'test'}, {}, None, {}),
        category=AssetCategory.acquired,
        source_kind=SourceKind.download,
    )

    with pytest.raises(RecsError, match='Asset is not a relative file'):
        session_export.export(record, tmp_path / 'unapproved')

    assert (
        session_export.main(
            [str(record), str(tmp_path / 'export'), '--asset-policy', str(policy)]
        )
        == 0
    )

    exported = tmp_path / 'export' / 'recording.toml'
    copied = read_recording(exported)
    asset = next(a for a in copied.assets if a.name == audio_asset_name)
    assert asset.location == RelativeFileLocation(path=f'assets/{audio_asset_name}')
    assert (exported.parent / asset.location.path).read_bytes() == original
    assert session_record_check.check(exported) == []


def test_export_does_not_replace_destination_created_during_publication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    record = _record(tmp_path / 'a', 0, None, None)
    destination = tmp_path / 'export'
    publish = session_export._publish_directory

    def create_destination_before_publish(temporary: Path, target: Path) -> None:
        target.mkdir()
        (target / 'keep').write_text('unrelated')
        publish(temporary, target)

    monkeypatch.setattr(
        session_export, '_publish_directory', create_destination_before_publish
    )

    with pytest.raises(RecsError, match='Export not published; staging retained'):
        session_export.export(record, destination)

    assert (destination / 'keep').read_text() == 'unrelated'
    staging = list(tmp_path.glob('.export.recs-export-*'))
    assert len(staging) == 1
    assert (staging[0] / 'export-progress.json').exists()


@pytest.mark.parametrize('interrupt', [OSError, KeyboardInterrupt])
def test_resume_reuses_verified_files_and_restarts_partial_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, interrupt: type[BaseException]
) -> None:
    record, staging = _interrupt_export(tmp_path, monkeypatch, interrupt)
    progress = json.loads((staging / 'export-progress.json').read_text())
    assert len(progress['copied']) == len(progress['remaining']) == 1
    assert progress['failed'] == progress['remaining']
    assert progress['verified'] == []
    copied: list[str] = []
    original_copy = session_export.shutil.copy2

    def copy(source: Path, destination: Path) -> None:
        copied.append(destination.relative_to(staging).as_posix())
        original_copy(source, destination)

    monkeypatch.setattr(session_export.shutil, 'copy2', copy)
    result = session_export.export(record, tmp_path / 'export', staging)
    assert copied == progress['remaining']
    assert not staging.exists()
    assert session_record_check.check(result / 'recording.toml') == []
    finished = json.loads((result / 'export-progress.json').read_text())
    assert finished['verified'] == progress['copied']
    assert finished['copied'] == progress['remaining']
    assert finished['remaining'] == finished['failed'] == []
    monkeypatch.undo()
    clean = session_export.export(record, tmp_path / 'clean')
    assert {
        p.relative_to(result): p.read_bytes()
        for p in result.rglob('*')
        if p.is_file() and p.name != 'export-progress.json'
    } == {
        p.relative_to(clean): p.read_bytes()
        for p in clean.rglob('*')
        if p.is_file() and p.name != 'export-progress.json'
    }


@pytest.mark.parametrize('change', ['document', 'completed', 'destination', 'symlink'])
def test_resume_rejects_changed_or_unrelated_work_without_overwriting(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, change: str
) -> None:
    record, staging = _interrupt_export(tmp_path, monkeypatch, OSError)
    manifest = staging / 'export-progress.json'
    evidence = manifest.read_bytes()
    progress = json.loads(evidence)
    completed = staging / progress['copied'][0]
    target = tmp_path / 'export'
    match = ''
    if change == 'document':
        with record.open('a') as output:
            output.write('\n# modified document\n')
        match = 'different source documents'
    elif change == 'completed':
        completed.write_bytes(b'corruption')
        match = 'Completed staged asset differs'
    elif change == 'destination':
        target.mkdir()
        (target / 'keep').write_text('unrelated')
        match = 'already exists'
    else:
        completed.rename(completed.with_suffix('.saved'))
        completed.symlink_to(record.parent / progress['copied'][0])
        match = 'Unsafe staged export path'
    before = {p: p.read_bytes() for p in record.parent.iterdir() if p.is_file()}
    with pytest.raises(RecsError, match=match):
        session_export.export(record, target, staging)
    assert manifest.read_bytes() == evidence
    assert {p: p.read_bytes() for p in record.parent.iterdir() if p.is_file()} == before
    if change == 'destination':
        assert (target / 'keep').read_text() == 'unrelated'
    else:
        assert not target.exists()


def test_export_refuses_unrecognized_staging(tmp_path: Path) -> None:
    record = _record(tmp_path / 'a', 0, None, None)
    staging = tmp_path / 'unrelated'
    staging.mkdir()
    (staging / 'keep').write_text('keep')
    with pytest.raises(RecsError, match='Cannot read export staging progress'):
        session_export.export(record, tmp_path / 'export', staging)
    assert list(staging.iterdir()) == [staging / 'keep']


def _interrupt_export(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, interrupt: type[BaseException]
) -> tuple[Path, Path]:
    record = _record(tmp_path / 'a', 0, None, None)
    original_copy = session_export.shutil.copy2
    copies = 0

    def copy(source: Path, destination: Path) -> None:
        nonlocal copies
        copies += 1
        if copies == 2:
            destination.write_bytes(b'partial')
            raise interrupt('copy interrupted')
        original_copy(source, destination)

    monkeypatch.setattr(session_export.shutil, 'copy2', copy)
    with pytest.raises(RecsError, match='staging retained'):
        session_export.export(record, tmp_path / 'export')
    monkeypatch.undo()
    assert not (tmp_path / 'export').exists()
    stages = list(tmp_path.glob('.export.recs-export-*'))
    assert len(stages) == 1
    return record, stages[0]


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
