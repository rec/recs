from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
import soundfile
import tyro

from recs.edit import commands, session
from recs.edit.cli import EditCli, main
from recs.edit.schema import EditSpec, canonical_toml
from recs.ui import session_record


def test_edit_cli_parses_inputs_and_authored_times() -> None:
    cfg = tyro.cli(
        EditCli,
        args=['session-record.jsonl', '--start', '250ms', '--end', '1.5s'],
    )

    assert cfg.inputs == [Path('session-record.jsonl')]
    assert cfg.start == 0.25
    assert cfg.end == 1.5


def test_edit_cli_accepts_multiple_inputs() -> None:
    cfg = tyro.cli(EditCli, args=['one.wav', 'two.wav'])

    assert cfg.inputs == [Path('one.wav'), Path('two.wav')]


def test_edit_cli_inputs_are_optional() -> None:
    cfg = tyro.cli(EditCli, args=[])

    assert cfg.inputs == []


def test_dry_run_prints_only_canonical_toml(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    edit = EditSpec(schema_version=1, sample_rate=48_000)
    recipe = edit.model_dump(mode='json')
    command_path = tmp_path / 'command.toml'
    monkeypatch.setattr(
        commands, 'resolve_command', lambda command, cwd: (recipe, command_path)
    )
    monkeypatch.setattr(
        session,
        'prepare_edit',
        lambda complete, edit_directory, destination: SimpleNamespace(edit=complete),
    )
    monkeypatch.chdir(tmp_path)

    assert main(['command', '--dry-run']) == 0

    assert capsys.readouterr().out == canonical_toml(edit)
    assert list(tmp_path.iterdir()) == []


def test_dry_run_accepts_direct_audio_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    path = tmp_path / 'voice.wav'
    soundfile.write(path, np.zeros(48_000), 48_000, subtype='FLOAT')
    monkeypatch.chdir(tmp_path)

    assert main(['clip', 'voice.wav', '--dry-run']) == 0

    output = capsys.readouterr().out
    assert 'file = "../voice.wav"' in output
    assert 'channels = [1]' in output
    assert sorted(p.name for p in tmp_path.iterdir()) == ['voice.wav']


def test_edit_renders_direct_audio_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / 'voice.wav'
    audio = np.linspace(-0.5, 0.5, 48_000, dtype=np.float32)
    soundfile.write(path, audio, 48_000, subtype='FLOAT')
    monkeypatch.chdir(tmp_path)

    assert main(['clip', 'voice.wav', '--destination', 'result']) == 0

    rendered, sample_rate = soundfile.read(
        tmp_path / 'result/audio/voice.flac', dtype='float32'
    )
    assert sample_rate == 48_000
    np.testing.assert_allclose(rendered, audio, atol=2**-23)
    assert (tmp_path / 'result/session-record.jsonl').is_file()


def test_composition_cli_dry_run_accepts_reserved_and_direct_forms(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    record_path = tmp_path / 'session-record.jsonl'
    writer = session_record.SessionRecordWriter(record_path, started_at='start')
    writer.close()
    composition_path = tmp_path / 'composition.toml'
    composition_path.write_text('schema_version = 1\nkind = "composition"\n')
    monkeypatch.chdir(tmp_path)

    assert main(['compose', 'composition.toml', '--dry-run']) == 0
    reserved = capsys.readouterr().out
    assert main(['composition.toml', '--dry-run']) == 0

    assert capsys.readouterr().out == reserved
    assert 'Edits: none' in reserved
    assert f'Result: {record_path.resolve()}' in reserved
