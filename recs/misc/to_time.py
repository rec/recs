from recs.misc import RecsError


def to_time(t: str) -> float:
    try:
        parts = t.split(':')
        if not (1 <= len(parts) <= 3):
            raise ValueError

        s = float(parts.pop())
        if s < 0:
            raise ValueError

        if not parts:
            return s

        if s >= 60:
            raise ValueError

        m = int(parts.pop())
        if m < 0:
            raise ValueError

        s += 60 * m
        if not parts:
            return s

        if m >= 60:
            raise ValueError

        h = int(parts.pop())
        if h < 0:
            raise ValueError

        assert not parts

        return s + 3600 * h

    except Exception:
        pass

    raise RecsError(f'Do not understand --longest-file-time={t}')
