import typing as t

from recs.misc import RecsError

RECS_USES = {'date', 'software', 'tracknumber'}
USABLE = {'album', 'artist', 'comment', 'copyright', 'genre', 'title'}
UNUSABLE = {'license'}  # Can't be set for some reason
ALL = RECS_USES | USABLE | UNUSABLE


def to_dict(metadata: t.Sequence[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    errors: dict[str, list[str]] = {}

    for m in metadata:
        name, eq, value = (i.strip() for i in m.partition('='))
        if not (name and eq and value):
            errors.setdefault('malformed', []).append(m)
        elif name in result:
            errors.setdefault('duplicate', []).append(m)
        elif name not in ALL:
            errors.setdefault('unknown', []).append(m)
        elif name not in USABLE:
            errors.setdefault('not settable', []).append(m)
        else:
            result[name] = value

    if errors:
        msg = ', '.join(f'{k}: {v}' for k, v in errors.items())
        raise RecsError('Metadata: ' + msg)

    return result
