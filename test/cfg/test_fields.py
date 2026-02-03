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
    had = {h.name: (h.default, a.default) for h, a in zip(hand, auto, strict=False)}

    differences = {k: (h, a) for k, (h, a) in had.items() if h != a}
    differences.pop('files')
    assert not differences
    # Work around dtyper.

    actual = [(h.type, a.type) for h, a in zip(hand, auto, strict=False)]
    ok = (
        (t.Sequence[str], list[str]),
        (str, types.Format),
        (str, types.SdType | None),
        (str, types.Subtype | None),
        (float, str),
        (t.Sequence[str], t.List[types.Format]),
    )

    bad = [(h, a) for h, a in actual if h != a and (h, a) not in ok]
    assert not bad
