import typing as t

import pytest
import tyro

from recs.base import cfg_raw
from recs.cfg import cli, run_cli


def test_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    parsed: dict[str, t.Any] = {}

    def make_cfg(**kwargs: t.Any) -> dict[str, t.Any]:
        parsed.update(kwargs)
        return parsed

    def consume(cfg: t.Any) -> None:
        assert cfg is parsed

    monkeypatch.setattr(cli.cfg, 'Cfg', make_cfg)
    monkeypatch.setattr(run_cli, 'run_cli', consume)

    tyro.cli(cli.recs, args=[])

    assert tuple(parsed) == tuple(cfg_raw.CfgRaw.model_fields)
    assert cfg_raw.CfgRaw(**parsed) == cfg_raw.CfgRaw()
