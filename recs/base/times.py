import time

sleep = time.sleep
timestamp = time.time


def to_time(t: str) -> float:
    parts = t.split(':')
    if not (1 <= len(parts) <= 3):
        raise ValueError('A time can only have three parts')

    s = float(parts.pop())
    if s < 0:
        raise ValueError('TimeSettings cannot be negative')

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
    m, s = divmod(dt, 60)
    m = int(m)
    h, m = divmod(m, 60)
    t = f'{s:06.3f}'
    if h:
        return f'{h}:{m:02}:{t}'
    if m:
        return f'{m}:{t}'
    return f'{s:.3f}'
