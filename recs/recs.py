import dataclasses as dc
import json
import sys
import typing as t
from pathlib import Path

import click
import dtyper
import sounddevice as sd
from typer import rich_utils

from . import RecsError
from .audio.channel_writer import TIMESTAMP_FORMAT
from .audio.file_types import DTYPE, DType, Format, Subtype

rich_utils.STYLE_METAVAR = 'dim yellow'
ICON = '🎙'
CLI_NAME = 'recs'

app = dtyper.Typer(
    add_completion=False,
    context_settings={'help_option_names': ['--help', '-h']},
    help=f"""\
{ICON} {CLI_NAME} {ICON}

Usage: {CLI_NAME} [GLOBAL-FLAGS] [COMMAND] [COMMAND-FLAGS] [COMMAND-ARGS]
""",
)
VERBOSE = False
_SINGLES: set[str] = set()


def Option(default, *a, **ka) -> dtyper.Option:
    _SINGLES.update(i[1] for i in a if len(i) == 2)
    return dtyper.Option(default, *a, **ka)


@dc.dataclass(frozen=True)
class Recording:
    #
    # General purpose settings
    #
    dry_run: bool = False
    info: bool = False
    path: Path = Path()
    retain: bool = False
    timestamp_format: str = TIMESTAMP_FORMAT
    verbose: bool = False
    #
    # Aliases for input devices or channels
    #
    alias: t.Sequence[str] = ()
    #
    # Exclude or include devices or channels
    #
    exclude: t.Sequence[str] = ()
    include: t.Sequence[str] = ()
    #
    # Audio file format and subtype
    #
    format: Format = Format.FLAC
    subtype: Subtype = Subtype.none
    dtype: DType = DTYPE
    #
    # Console and UI settings
    #
    ui_refresh_rate: float = 23
    sleep_time: float = 0.013
    #
    # Settings relating to times
    #
    silence_before_start: float = 1
    silence_after_end: float = 2
    stop_after_silence: float = 20
    noise_floor: float = 70
    total_run_time: float = 0

    def __call__(self) -> None:
        if self.info:
            info = sd.query_devices(kind=None)
            print(json.dumps(info, indent=2))
        else:
            from .ui.session import Session

            Session(self).run()


@app.command(help='Record everything coming in')
def recs(
    #
    # General purpose settings
    #
    dry_run: bool = Option(
        False, '-n', '--dry-run', help='Display levels only, do not record'
    ),
    info: bool = Option(
        False, '--info', help='Do not run, display device info instead'
    ),
    path: Path = Option(
        Path(), '-p', '--path', help='Path to the parent directory for files'
    ),
    retain: bool = Option(
        False, '-r', '--retain', help='Retain rich display on shutdown'
    ),
    timestamp_format: str = Option(
        TIMESTAMP_FORMAT, help='Format string for timestamps'
    ),
    verbose: bool = Option(False, '-v', '--verbose', help='Print full stack traces'),
    #
    # Aliases for input devices or channels
    #
    alias: list[str] = Option(
        (), '-a', '--alias', help='Aliases for devices or channels'
    ),
    #
    # Exclude or include devices or channels
    #
    exclude: list[str] = Option(
        None, '-e', '--exclude', help='Exclude these devices or channels'
    ),
    include: list[str] = Option(
        None, '-i', '--include', help='Only include these devices or channels'
    ),
    #
    # Audio file format and subtype
    #
    format: Format = Option(Format.FLAC, '-f', '--format', help='Audio format'),
    subtype: Subtype = Option(Subtype.none, '-u', '--subtype', help='File subtype'),
    dtype: DType = Option(DTYPE, '-d', '--dtype', help='Type of numpy numbers'),
    #
    # Console and UI settings
    #
    ui_refresh_rate: float = Option(
        23, '--ui-refresh-rate', help='How many UI refreshes per second'
    ),
    sleep_time: float = Option(
        0.013, '--sleep-time', help='How long to sleep between data refreshes'
    ),
    #
    # Settings relating to times
    #
    silence_before_start: float = Option(
        1, '-b', '--silence-before-start', help='Silence before the start, in seconds'
    ),
    silence_after_end: float = Option(
        2, '-c', '--silence-after-end', help='Silence after the end, in seconds'
    ),
    stop_after_silence: float = Option(
        20, '-s', '--stop-after-silence', help='Stop recording after silence'
    ),
    noise_floor: float = Option(
        70, '-o', '--noise-floor', help='The noise floor in decibels'
    ),
    total_run_time: float = Option(
        0, '-t', '--total-run-time', help='How many seconds to record? 0 means forever'
    ),
) -> None:
    global VERBOSE
    VERBOSE = verbose

    format = Format[format.strip('.').upper()]
    Recording(**locals())()


EXPECTED_SINGLES = 'abcdefinoprstuv'
_ACTUAL_SINGLES = ''.join(sorted(_SINGLES))
assert _ACTUAL_SINGLES == EXPECTED_SINGLES, _ACTUAL_SINGLES


def run() -> int:
    try:
        app(standalone_mode=False)
        return 0

    except RecsError as e:
        print('ERROR:', *e.args, file=sys.stderr)

    except click.ClickException as e:
        print(f'{e.__class__.__name__}: {e.message}', file=sys.stderr)

    except click.Abort:
        print('Aborted', file=sys.stderr)

    except KeyboardInterrupt:
        print('Interrupted', file=sys.stderr)

    return -1
