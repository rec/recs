import json
import string
import sys
from pathlib import Path

import click
import dtyper
import sounddevice as sd
from typer import rich_utils

from . import RECS, RecsError
from .audio.file_types import DType, Format, Subtype
from .ui.recorder import Recorder

rich_utils.STYLE_METAVAR = 'dim yellow'
ICON = '🎬'
CLI_NAME = 'recs'

app = dtyper.Typer(
    add_completion=False,
    context_settings={'help_option_names': ['--help', '-h']},
    help=f"""\
{ICON} {CLI_NAME} {ICON}

Usage: {CLI_NAME} [GLOBAL-FLAGS] [COMMAND] [COMMAND-FLAGS] [COMMAND-ARGS]
""",
)
_SINGLES: set[str] = set()


def Option(default, *a, **ka) -> dtyper.Option:
    _SINGLES.update(i[1] for i in a if len(i) == 2)
    return dtyper.Option(default, *a, **ka)


@app.command(help='Record everything coming in')
def recs(
    #
    # General purpose settings
    #
    dry_run: bool = Option(
        RECS.dry_run, '-n', '--dry-run', help='Display levels only, do not record'
    ),
    info: bool = Option(
        RECS.info, '--info', help='Do not run, display device info instead'
    ),
    path: Path = Option(
        RECS.path, '-p', '--path', help='Path to the parent directory for files'
    ),
    retain: bool = Option(
        RECS.retain, '-r', '--retain', help='Retain rich display on shutdown'
    ),
    timestamp_format: str = Option(
        RECS.timestamp_format, help='Format string for timestamps'
    ),
    verbose: bool = Option(
        RECS.verbose, '-v', '--verbose', help='Print full stack traces'
    ),
    #
    # Aliases for input devices or channels
    #
    alias: list[str] = Option(
        RECS.alias, '-a', '--alias', help='Aliases for devices or channels'
    ),
    #
    # Exclude or include devices or channels
    #
    exclude: list[str] = Option(
        RECS.exclude, '-e', '--exclude', help='Exclude these devices or channels'
    ),
    include: list[str] = Option(
        RECS.include, '-i', '--include', help='Only include these devices or channels'
    ),
    #
    # Audio file format and subtype
    #
    format: Format = Option(RECS.format, '-f', '--format', help='Audio format'),
    subtype: Subtype = Option(RECS.subtype, '-u', '--subtype', help='File subtype'),
    dtype: DType = Option(RECS.dtype, '-d', '--dtype', help='Type of numpy numbers'),
    #
    # Console and UI settings
    #
    quiet: bool = Option(
        RECS.quiet, '-q', '--quiet', help='If true, do not display live updates'
    ),
    ui_refresh_rate: float = Option(
        RECS.ui_refresh_rate,
        '--ui-refresh-rate',
        help='How many UI refreshes per second',
    ),
    sleep_time: float = Option(
        RECS.sleep_time, '--sleep-time', help='How long to sleep between data refreshes'
    ),
    #
    # Settings relating to times
    #
    silence_before_start: float = Option(
        RECS.silence_before_start,
        '-b',
        '--silence-before-start',
        help='Silence before the start, in seconds',
    ),
    silence_after_end: float = Option(
        RECS.silence_after_end,
        '-c',
        '--silence-after-end',
        help='Silence after the end, in seconds',
    ),
    stop_after_silence: float = Option(
        RECS.stop_after_silence,
        '-s',
        '--stop-after-silence',
        help='Stop recs after silence',
    ),
    noise_floor: float = Option(
        RECS.noise_floor, '-o', '--noise-floor', help='The noise floor in decibels'
    ),
    total_run_time: float = Option(
        RECS.total_run_time,
        '-t',
        '--total-run-time',
        help='How many seconds to record? 0 means forever',
    ),
) -> None:
    for k, v in list(locals().items()):
        setattr(RECS, k, v)

    if RECS.info:
        info = sd.query_devices(kind=None)
        print(json.dumps(info, indent=2))
    else:
        Recorder().run()


_USED_SINGLES = ''.join(sorted(_SINGLES))
_UNUSED_SINGLES = ''.join(sorted(set(string.ascii_lowercase) - set(_SINGLES)))

assert _USED_SINGLES == 'abcdefinopqrstuv', _USED_SINGLES
assert _UNUSED_SINGLES == 'ghjklmwxyz', _UNUSED_SINGLES


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
