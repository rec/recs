import dataclasses as dc
import typing as t

import dtyper

import recs.base.cfg_raw
from recs.base import cli
from recs.base.types import SdType, Subtype


def test_fields():
    @dtyper.dataclass(cli.recs)
    class Cfg:
        pass

    hand, auto = dc.fields(recs.base.cfg_raw.CfgRaw), dc.fields(Cfg)

    assert [f.name for f in hand] == [f.name for f in auto]
    assert not [h.name for h, a in zip(hand, auto) if h.default != a.default]

    types = [(h.type, a.type) for h, a in zip(hand, auto)]
    ok = (
        (t.Sequence[str], list[str]),
        (SdType | None, SdType),
        (Subtype | None, Subtype),
    )

    assert all((h, a) in ok for h, a in types if h != a)
