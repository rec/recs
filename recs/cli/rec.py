from dtyper import Option

from recs.audio.format import Format
from recs.audio.subtype import Subtype

from .app import command

"""
* Include or exclude specific devices or channels
* File format
* Sample rate
* Directory to write to
* Display levels only
"""


@command(help='Record everything coming in')
def rec(
    format: Format = Option(Format.caf, '-F', '--format', help='File format to use'),
    subtype: Subtype = Option(
        Subtype.alac_24, '-f', '--subtype', help='File subtype to write to'
    ),
):
    pass
