import typing as t
from pathlib import Path

import dtyper
from dtyper import Option

from recs.audio.format import Format
from recs.audio.subtype import Subtype

from .app import command

"""
* Include or exclude specific devices or channels
* Channel assignments
"""


@command(help='Record everything coming in')
def rec(
    exclude: t.List[str] = Option(
        None, '-e', '--exclude', help='Exclude these devices or channels'
    ),
    include: t.List[str] = Option(
        None, '-i', '--include', help='Only include these devices or channels'
    ),
    format: Format = Option(
        Format.caf, '-f', '--format', help='Audio file format to use'
    ),
    subtype: Subtype = Option(
        Subtype.alac_24, '-t', '--subtype', help='File subtype to write to'
    ),
    path: Path = Option(
        Path(), '-p', '--path', help='Path to the parent directory for files'
    ),
    levels_only: bool = Option(
        False, '-l', '--levels', help='Display levels only, do not record'
    ),
    before_start: float = Option(
        1, '-b', '--before-start', help='Silence before the start, in seconds'
    ),
    after_end: float = Option(
        2, '-a', '--after-end', help='Silence after the end, in seconds'
    ),
    stop_after: float = Option(
        20,
        '-s',
        '--stop-after',
        help='Stop recording after silence',
    ),
    noise_floor: float = Option(
        70, '-n', '--noise-floor', help='The noise floor in decibels'
    ),
):
    Rec(**locals())()


@dtyper.dataclass(rec)
class Rec:
    def __call__(self):
        print(self)
