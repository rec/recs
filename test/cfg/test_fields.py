import typing as t

import pytest
import tyro

from recs.cfg import Cfg, cli, run_cli


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

    assert tuple(parsed) == tuple(Cfg.model_fields)
    assert Cfg(**parsed) == Cfg()
