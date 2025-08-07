import typing as t

from recs.base.types import Format


def header_size(metadata: t.Mapping[str, str], format: Format) -> int:
    if format != Format.wav:
        return 0

    tag = 9
    base, first, software = 44, 12, 19

    values = (software * (k == 'software') + tag + len(v) for k, v in metadata.items())
    values = (v + v % 2 for v in values)

    return base + first * bool(metadata) + sum(values)
