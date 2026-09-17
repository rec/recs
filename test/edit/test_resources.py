import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
import soundfile
from pytest_regressions.data_regression import DataRegressionFixture
from ufor.arrangement import ArrangementScore
from ufor.codec import score_toml
from ufor.encoding import Format, Subtype
from ufor.recording import Gap

from recs.base.errors import RecsError
from recs.edit import commands, materialized, resources, session, workspace
from recs.edit.cli import main
from recs.edit.composition import CompositionEdit, CompositionStep, composition_summary
from recs.edit.options import EditOptions
from recs.recording.read import read_recording


@pytest.fixture
def record(tmp_path: Path) -> Path:
    audio = tmp_path / 'voice.wav'
    soundfile.write(audio, np.linspace(-0.5, 0.5, 48_000), 48_000, subtype='FLOAT')
    recipe, _ = commands.resolve_command('clip', tmp_path)
    definitions = {}
    commands.complete_or_generate(recipe, [audio], EditOptions(), definitions)
    path = tmp_path / 'recording.toml'
    path.write_text(score_toml(next(iter(definitions.values()))))
    return path


def test_sparse_plan_uses_metadata_without_decoding_or_allocating(
    record: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    data_regression: DataRegressionFixture,
) -> None:
    document = read_recording(record)
    stream = document.body.streams[0].model_copy(
        update={
            'end': 4_800_000_000,
            'gaps': [Gap(start=48_000, end=4_800_000_000, reason='silence_suppressed')],
        }
    )
    document = document.model_copy(
        update={'body': document.body.model_copy(update={'streams': [stream]})}
    )
    record.write_text(score_toml(document))
    before = {p: p.read_bytes() for p in tmp_path.iterdir()}

    def forbidden(*args: object, **kwargs: object) -> None:
        pytest.fail('Planning must not decode or allocate audio')

    monkeypatch.setattr(materialized, 'AudioStorage', forbidden)
    monkeypatch.setattr(soundfile, 'SoundFile', forbidden)
    recipe, _ = commands.resolve_command('clip', tmp_path)
    definitions = {}
    edit = commands.complete_or_generate(
        recipe,
        [record],
        EditOptions(format=Format.wav, subtype=Subtype.float),
        definitions,
    )
    with workspace.audio_workspace(tmp_path):
        plan = resources.plan_edit(edit, Path.cwd(), tmp_path / 'output', definitions)
    assert {p: p.read_bytes() for p in tmp_path.iterdir()} == before
    data_regression.check(
        json.loads(plan.model_dump_json().replace(str(tmp_path), '<root>'))
    )


def test_composition_preview_propagates_metadata_and_stops_at_analysis(
    record: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden(*args: object, **kwargs: object) -> None:
        pytest.fail('Preview must not allocate audio storage')

    monkeypatch.setattr(materialized, 'AudioStorage', forbidden)
    value = CompositionEdit(
        schema_version=1,
        kind='composition',
        edits=[
            CompositionStep(command='clip'),
            CompositionStep(command='clip'),
            CompositionStep(command='autocalibrate'),
            CompositionStep(command='clip'),
        ],
    )
    before = set(tmp_path.iterdir())
    summary = composition_summary(
        value, tmp_path / 'compose.toml', record, tmp_path / 'out'
    )
    assert '1: clip' in summary and '2: clip' in summary
    assert 'Stage 3 calibration and subsequent stages require audio analysis' in summary
    assert 'Destination audio estimate: unknown' in summary
    assert set(tmp_path.iterdir()) == before


def test_nested_plan_counts_intermediates_without_rendering(
    record: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recipe, _ = commands.resolve_command('clip', tmp_path)
    child = commands.complete_or_generate(recipe, [record], EditOptions())
    raw = child.model_dump()
    for part in raw['body']['parts']:
        part['score']['path'] = Path(part['score']['path']).resolve().name
    child = ArrangementScore.model_validate(raw)
    path = tmp_path / 'nested.toml'
    path.write_text(score_toml(child))
    raw['body']['parts'] = [{'name': 'nested', 'score': {'path': path.name}}]
    raw['body']['clips'][0]['source'] = {
        'part': 'nested',
        'output': child.outputs[0].name,
    }
    outer = ArrangementScore.model_validate(raw)

    def forbidden(*args: object, **kwargs: object) -> None:
        pytest.fail('Nested planning must not read samples or allocate storage')

    monkeypatch.setattr(materialized, 'AudioStorage', forbidden)
    monkeypatch.setattr(soundfile, 'SoundFile', forbidden)
    plan = resources.plan_edit(outer, tmp_path, tmp_path / 'output')
    assert list(plan.output_frames.values()) == [48_000]
    assert plan.source_storage_bytes == 192_000
    assert plan.intermediate_storage_bytes == 384_000
    assert plan.destination_bytes is None
    assert plan.unknown


def test_scratch_selection_covers_sources_outputs_and_restores_default(
    record: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scratch = tmp_path / 'scratch'
    scratch.mkdir()
    directories: list[Path] = []
    temporary = materialized.TemporaryFile

    def capture(*, dir: Path) -> object:
        directories.append(dir)
        return temporary(dir=dir)

    monkeypatch.setattr(materialized, 'TemporaryFile', capture)
    target = tmp_path / 'output'
    assert (
        main(
            [
                'clip',
                str(record),
                '--scratch-directory',
                str(scratch),
                '--destination',
                str(target),
                '--format',
                'wav',
                '--subtype',
                'float',
            ]
        )
        == 0
    )
    assert len(directories) >= 2
    assert set(directories) == {scratch}
    assert workspace.SCRATCH_DIRECTORY.get() is None
    assert read_recording(target / 'recording.toml').body.state == 'sealed'


def test_insufficient_combined_space_fails_before_materialization(
    record: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recipe, _ = commands.resolve_command('clip', tmp_path)
    edit = commands.complete_or_generate(
        recipe, [record], EditOptions(format=Format.wav, subtype=Subtype.float)
    )

    def forbidden(*args: object, **kwargs: object) -> None:
        pytest.fail('No audio may be allocated after a failed preflight')

    monkeypatch.setattr(materialized, 'AudioStorage', forbidden)
    # Each component fits, but scratch plus output on one filesystem does not.
    monkeypatch.setattr(
        workspace.shutil, 'disk_usage', lambda path: SimpleNamespace(free=400_000)
    )
    target = tmp_path / 'output'
    with (
        workspace.audio_workspace(tmp_path),
        pytest.raises(RecsError, match='Insufficient space'),
    ):
        session.execute_edit(edit, Path.cwd(), target)
    assert not target.exists()


def test_scratch_write_failure_leaves_no_complete_session(
    record: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail(*args: object, **kwargs: object) -> None:
        raise OSError('disk full')

    monkeypatch.setattr(materialized, 'TemporaryFile', fail)
    target = tmp_path / 'output'
    with pytest.raises(RecsError, match='temporary audio storage'):
        main(
            [
                'clip',
                str(record),
                '--destination',
                str(target),
                '--scratch-directory',
                str(tmp_path),
            ]
        )
    assert not target.exists()
    assert workspace.SCRATCH_DIRECTORY.get() is None
