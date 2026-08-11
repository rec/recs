from typing import Any

import pytest
import tyro

from recs.cfg import cfg, cli, run_cli
from recs.cfg.cfg import Cfg


def test_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    parsed: dict[str, Any] = {}

    def make_cfg(**kwargs: Any) -> dict[str, Any]:
        parsed.update(kwargs)
        return parsed

    def consume(cfg: Any) -> None:
        assert cfg is parsed

    monkeypatch.setattr(cli.cfg, 'Cfg', make_cfg)
    monkeypatch.setattr(run_cli, 'run_cli', consume)

    tyro.cli(cli.recs, args=[])

    assert tuple(parsed) == tuple(cfg.FLAT_FIELDS)
    assert Cfg(**parsed) == Cfg()
