import inspect
import typing as t

from recs.base import cfg_raw, types
from recs.cfg import cli


def test_fields():
    hand = tuple(cfg_raw.CfgRaw.model_fields.items())
    auto = tuple(inspect.signature(cli.recs).parameters.items())

    assert [name for name, _ in hand] == [name for name, _ in auto]
    had = {
        name: (h.get_default(call_default_factory=True), a.default)
        for (name, h), (_, a) in zip(hand, auto, strict=False)
    }

    differences = {k: (h, a) for k, (h, a) in had.items() if h != a}
    differences.pop('files')
    differences.pop('formats')
    assert not differences
    # Work around dtyper.

    actual = [
        (h.annotation, a.annotation)
        for (_, h), (_, a) in zip(hand, auto, strict=False)
    ]
    ok = (
        (str | None, types.SdType | None),
        (str | None, types.Subtype | None),
        (float, str),
        (list[str], t.List[types.Format]),
    )

    bad = [(h, a) for h, a in actual if h != a and (h, a) not in ok]
    assert not bad
