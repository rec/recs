import dataclasses as dc
import typing as t

import dtyper

from recs.base import cfg_raw, types
from recs.cfg import cli


def test_fields():
    @dtyper.dataclass(cli.recs)
    class Cfg:
        pass

    hand, auto = dc.fields(cfg_raw.CfgRaw), dc.fields(Cfg)

    assert [f.name for f in hand] == [f.name for f in auto]
    had = {h.name: (h.default, a.default) for h, a in zip(hand, auto)}
    assert not {k: (h, a) for k, (h, a) in had.items() if h != a}

    actual = [(h.type, a.type) for h, a in zip(hand, auto)]
    ok = (
        (t.Sequence[str], list[str]),
        (types.SdType | None, types.SdType),
        (types.Subtype | None, types.Subtype),
        (float, str),
    )

    assert all((h, a) in ok for h, a in actual if h != a)
