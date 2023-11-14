from recs.base.types import Format


def header_size(metadata: dict[str, str], format: Format) -> int:
    tag = 9
    if format == Format.aiff:
        base, first, software = 54, 0, 22
    elif format == Format.wav:
        base, first, software = 44, 12, 19
    else:
        return 0

    values = (software * (k == 'software') + tag + len(v) for k, v in metadata.items())
    values = (v + v % 2 for v in values)

    return base + first * bool(metadata) + sum(values)
