import re
import string
from datetime import datetime
from enum import IntEnum, auto

from recs.base import RecsError
from recs.cfg import aliases, track

findall_strftime = re.compile('%.').findall


def parse_fields(s: str) -> list[str]:
    return sorted(n for _, n, _, _ in string.Formatter().parse(s) if n)


class Req(IntEnum):
    device = auto()
    channel = auto()
    year = auto()
    month = auto()
    day = auto()
    hour = auto()
    minute = auto()
    second = auto()


class PathPattern:
    def __init__(self, path: str) -> None:
        str_parts = parse_fields(path)
        time_parts = findall_strftime(path)
        parts = set(time_parts + str_parts)

        if bad := parts - FIELDS:
            raise RecsError(f'Unknown: {", ".join(sorted(bad))}')

        self.name_parts = tuple(i for i in str_parts if i not in FIELD_TO_PSTRING)
        self.pstring_parts = tuple(i for i in str_parts if i in FIELD_TO_PSTRING)

        used = set().union(*(FIELD_TO_REQUIRED[p] for p in parts))
        unused = set(Req) - used

        def rep(r: Req) -> str:
            return (r in unused) * f'{{{r.name}}}'

        y, m, d = rep(Req.year), rep(Req.month), rep(Req.day)
        if (m and not (y or d)) or (not m and (y and d)):
            raise RecsError(f'Must specify year or day with month: {path}')
        date = y + m + d

        h, m, s = rep(Req.hour), rep(Req.minute), rep(Req.second)
        if (m and not (h or s)) or (not m and (h and s)):
            raise RecsError(f'Must specify hour or second with minute: {path}')
        time = h + m + s

        d, c = rep(Req.device), rep(Req.channel)
        dc = '{track}' if all((d, c)) else d + c

        dt = f'{date}-{time}' if all((date, time)) else date + time
        p = f'{dc} + {dt}' if all((dc, dt)) else dc + dt

        self.path = f'{path}/{p}' if all((path, p)) else path + p

        str_parts = parse_fields(self.path)
        self.strf_parts = tuple(i for i in str_parts if i in FIELD_TO_PSTRING)

    def times(self, ts: datetime) -> dict[str, str]:
        return {k: ts.strftime(FIELD_TO_PSTRING[k]) for k in self.strf_parts}

    def evaluate(
        self,
        track: track.Track,
        aliases: aliases.Aliases,
        timestamp: float,
        index: int,
    ) -> str:
        ts = datetime.fromtimestamp(timestamp)
        s = ts.strftime(self.path)

        return s.format(
            channel=track.name,
            device=aliases.display_name(track.device),
            index=str(index),
            track=aliases.display_name(track, short=False),
            **self.times(ts),
        )


DATE = {Req.year, Req.month, Req.day}
TIME = {Req.hour, Req.minute, Req.second}

FIELD_TO_REQUIRED: dict[str, set[Req]] = {
    'index': DATE | TIME,
    'device': {Req.device},
    'channel': {Req.channel},
    'track': {Req.channel, Req.device},
    #
    'date': DATE,
    'time': TIME,
    'ddate': DATE,
    'dtime': TIME,
    'sdate': DATE,
    'stime': TIME,
    'timestamp': DATE | TIME,
    #
    'year': {Req.year},
    'month': {Req.month},
    'day': {Req.day},
    'hour': {Req.hour},
    'minute': {Req.minute},
    'second': {Req.second},
    #
    '%A': set(),
    '%B': {Req.month},
    '%G': {Req.year},
    '%H': {Req.hour},
    '%I': set(),
    '%M': {Req.minute},
    '%S': {Req.second},
    '%U': set(),
    '%V': set(),
    '%W': set(),
    '%X': TIME,
    '%Y': {Req.year},
    '%Z': set(),
    '%a': set(),
    '%b': {Req.month},
    '%c': DATE | TIME,
    '%d': {Req.day},
    '%f': set(),
    '%j': {Req.month, Req.day},
    '%m': {Req.month},
    '%p': set(),
    '%u': set(),
    '%w': set(),
    '%x': DATE,
    '%y': {Req.year},
    '%%': set(),
}
FIELDS = set(FIELD_TO_REQUIRED)

FIELD_TO_PSTRING: dict[str, str] = {
    'date': '%Y%m%d',
    'time': '%H%M%S',
    'ddate': '%Y-%m-%d',
    'dtime': '%H-%M-%S',
    'sdate': '%Y/%m/%d',
    'stime': '%H/%M/%S',
    'timestamp': '%H%M%S_Y%m%d',
    #
    'year': '%Y',
    'month': '%m',
    'day': '%d',
    'hour': '%H',
    'minute': '%M',
    'second': '%S',
}
