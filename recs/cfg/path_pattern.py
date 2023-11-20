import re
import string
from datetime import datetime
from enum import IntEnum, auto

from recs.base import RecsError

parse_fields = string.Formatter().parse
findall_strftime = re.compile('%.').findall


class Required(IntEnum):
    # Order is significant
    device = auto()
    channel = auto()
    year = auto()
    month = auto()
    day = auto()
    hour = auto()
    minute = auto()
    second = auto()


R = Required
DATE = {R.year, R.month, R.day}
TIME = {R.hour, R.minute, R.second}

FIELD_TO_REQUIRED: dict[str, set[R]] = {
    'index': set(),
    'device': {R.device},
    'channel': {R.channel},
    'track': {R.channel, R.device},
    #
    'date': DATE,
    'time': TIME,
    'ddate': DATE,
    'dtime': TIME,
    'sdate': DATE,
    'stime': TIME,
    'timestamp': DATE | TIME,
    'iso': DATE | TIME,
    #
    'year': {R.year},
    'month': {R.month},
    'day': {R.day},
    'hour': {R.hour},
    'minute': {R.minute},
    'second': {R.second},
    #
    '%A': set(),
    '%B': {R.month},
    '%G': {R.year},
    '%H': {R.hour},
    '%I': set(),
    '%M': {R.minute},
    '%S': {R.second},
    '%U': set(),
    '%V': set(),
    '%W': set(),
    '%X': TIME,
    '%Y': {R.year},
    '%Z': set(),
    '%a': set(),
    '%b': {R.month},
    '%c': DATE | TIME,
    '%d': {R.day},
    '%f': set(),
    '%j': {R.month, R.day},
    '%m': {R.month},
    '%p': set(),
    '%u': set(),
    '%w': set(),
    '%x': DATE,
    '%y': {R.year},
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


class PathPattern:
    def __init__(self, path: str) -> None:
        self.path = path

        str_parts = [n for _, n, _, _ in parse_fields(path) if n]
        time_parts = findall_strftime(path)
        parts = set(time_parts + str_parts)

        if bad := parts - FIELDS:
            raise RecsError(f'Unknown: {", ".join(sorted(bad))}')

        self.name_parts = tuple(i for i in str_parts if i not in FIELD_TO_PSTRING)
        self.pstring_parts = tuple(i for i in str_parts if i in FIELD_TO_PSTRING)

        used = set().union(*(FIELD_TO_REQUIRED[p] for p in parts))
        self.fields = tuple(sorted(set(Required) - used))

    def times(self, ts: datetime) -> dict[str, str]:
        return {k: ts.strftime(FIELD_TO_PSTRING[k]) for k in self.pstring_parts}
