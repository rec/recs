from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
import soundfile
import tyro
from ufor.arrangement import Arrangement, ArrangementDocument
from ufor.codec import document_toml
from ufor.time import Rate, Timebase

from recs.edit import commands, session
from recs.edit.cli import EditCli, main
from recs.recording.finalize import finalize_recording
from recs.ui import session_record


def test_edit_cli_parses_inputs_and_authored_times() -> None:
    cfg = tyro.cli(
        EditCli,
        args=['recording.toml', '--start', '250ms', '--end', '1.5s'],
    )

    assert cfg.inputs == [Path('recording.toml')]
    assert cfg.start == 0.25
    assert cfg.end == 1.5


def test_edit_cli_accepts_multiple_inputs() -> None:
    cfg = tyro.cli(EditCli, args=['one.wav', 'two.wav'])

    assert cfg.inputs == [Path('one.wav'), Path('two.wav')]


def test_edit_cli_inputs_are_optional() -> None:
    cfg = tyro.cli(EditCli, args=[])

    assert cfg.inputs == []


def test_dry_run_prints_only_document_toml(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    edit = ArrangementDocument(
        id='edit',
        name='Audio edit',
        timebases=[Timebase(id='audio', rate=Rate(numerator=48000))],
        body=Arrangement(
            timebase='audio',
        ),
    )
    recipe = edit.model_dump(mode='json')
    command_path = tmp_path / 'command.toml'
    monkeypatch.setattr(
        commands, 'resolve_command', lambda command, cwd: (recipe, command_path)
    )
    monkeypatch.setattr(
        session,
        'prepare_edit',
        lambda complete, edit_directory, destination, definitions: SimpleNamespace(
            edit=complete
        ),
    )
    monkeypatch.chdir(tmp_path)

    assert main(['command', '--dry-run']) == 0

    assert capsys.readouterr().out == document_toml(edit)
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
    assert '.recording.toml' in output
    assert 'definition' in output
    assert 'channels = ["channel-0"]' in output
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
    assert (tmp_path / 'result/recording.toml').is_file()


def test_composition_cli_dry_run_accepts_reserved_and_direct_forms(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    record_path = tmp_path / 'recording.toml'
    writer = session_record.SessionRecordWriter(
        (record_path).with_name('session-record.jsonl'), started_at='start'
    )
    writer.close()
    finalize_recording(writer.path)
    composition_path = tmp_path / 'composition.toml'
    composition_path.write_text('schema_version = 1\nkind = "composition"\n')
    monkeypatch.chdir(tmp_path)

    assert main(['compose', 'composition.toml', '--dry-run']) == 0
    reserved = capsys.readouterr().out
    assert main(['composition.toml', '--dry-run']) == 0

    assert capsys.readouterr().out == reserved
    assert 'Edits: none' in reserved
    assert f'Result: {record_path.resolve()}' in reserved
