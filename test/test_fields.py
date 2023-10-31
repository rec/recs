import dataclasses as dc
import typing as t

import dtyper

from recs import cfg, cli
from recs.audio.file_types import SdType, Subtype


@dtyper.dataclass(cli.recs)
class Recs:
    pass


def test_fields():
    hand, auto = dc.fields(cfg.Cfg), dc.fields(cfg.Cfg)

    assert [f.name for f in hand] == [f.name for f in auto]
    assert not [h.name for h, a in zip(hand, auto) if h.default != a.default]

    types = [(h.type, a.type) for h, a in zip(hand, auto)]
    ok = (
        (t.Sequence[str], list[str]),
        (SdType | None, SdType),
        (Subtype | None, Subtype),
    )

    assert all((h, a) in ok for h, a in types if h != a)
