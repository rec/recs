from pathlib import Path

import tyro

from recs.edit.cli import EditCli


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
