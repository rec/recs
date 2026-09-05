from pathlib import Path
from types import SimpleNamespace

import pytest
import tyro

from recs.edit import commands, session
from recs.edit.cli import EditCli, main
from recs.edit.schema import EditSpec, canonical_toml


def test_edit_cli_parses_record_and_authored_times() -> None:
    cfg = tyro.cli(
        EditCli,
        args=['session-record.jsonl', '--start', '250ms', '--end', '1.5s'],
    )

    assert cfg.record == Path('session-record.jsonl')
    assert cfg.start == 0.25
    assert cfg.end == 1.5


def test_edit_cli_record_is_optional() -> None:
    cfg = tyro.cli(EditCli, args=[])

    assert cfg.record is None


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
