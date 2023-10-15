import dataclasses as dc
import typing as t

import dtyper

from recs import cli, recs


@dtyper.dataclass(cli.recs)
class Recs:
    pass


def test_fields():
    hand, auto = dc.fields(recs.Recs), dc.fields(Recs)

    assert [f.name for f in hand] == [f.name for f in auto]
    assert not [h.name for h, a in zip(hand, auto) if h.default != a.default]

    types = [(h.type, a.type) for h, a in zip(hand, auto)]
    ok = t.Sequence[str], list[str]

    assert all((h, a) == ok for h, a in types if h != a)
