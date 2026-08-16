import tyro

from recs.cfg import cfg, cli
from recs.cfg.cfg import Cfg


def test_fields() -> None:
    parsed = tyro.cli(cli.CliCfg, args=[])
    fields = {
        name
        for part in cfg.CFG_PARTS
        for name in type(getattr(parsed, part)).model_fields
    }

    assert fields == set(cfg.FLAT_FIELDS)
    assert parsed == Cfg()
