def to_time(t: str) -> float:
    parts = t.split(':')
    if not (1 <= len(parts) <= 3):
        raise ValueError('A time can only have three parts')

    s = float(parts.pop())
    if s < 0:
        raise ValueError('Times cannot be negative')

    if not parts:
        return s

    if s > 59:
        raise ValueError('Seconds cannot be greater than 59')

    m = int(parts.pop())
    if m < 0:
        raise ValueError('Minutes cannot be negative')

    s += 60 * m
    if not parts:
        return s

    if m > 59:
        raise ValueError('Minutes cannot be greater than 59')

    h = int(parts.pop())
    if h < 0:
        raise ValueError('Hours cannot be negative')

    assert not parts
    return s + 3600 * h


def to_str(dt: float | int) -> str:
    if not isinstance(dt, (float, int)):
        return dt
    m, s = divmod(dt, 60)
    m = int(m)
    h, m = divmod(m, 60)
    return f'{h}:{m:02}:{s:02.3f}'
