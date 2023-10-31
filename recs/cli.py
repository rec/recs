import string
import sys
from pathlib import Path

import click
import dtyper
from typer import rich_utils

from recs import Cfg
from recs.misc import RecsError

from .audio.file_types import Format, SdType, Subtype

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

RECS = Cfg()
# Reading configs and environment variables would go here


def Option(default, *a, **ka) -> dtyper.Option:
    _SINGLES.update(i[1] for i in a if len(i) == 2)
    return dtyper.Option(default, *a, **ka)


@app.command(help='Record everything coming in')
def recs(
    #
    # Directory settings
    #
    path: Path = Option(
        RECS.path, '-p', '--path', help='Path to the parent directory for files'
    ),
    subdirectory: list[str] = Option(
        RECS.subdirectory,
        '-s',
        '--subdirectory',
        help='Organize files by date, device or both',
    ),
    #
    # General purpose settings
    #
    dry_run: bool = Option(
        RECS.dry_run, '-n', '--dry-run', help='Display levels only, do not record'
    ),
    info: bool = Option(
        RECS.info, '--info', help='Do not run, display device info instead'
    ),
    list_subtypes: bool = Option(
        RECS.list_subtypes, '--list-subtypes', help='List all subtypes for each format'
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
    sdtype: SdType = Option(
        RECS.sdtype, '-d', '--sdtype', help='Type of sounddevice numbers'
    ),
    subtype: Subtype = Option(RECS.subtype, '-u', '--subtype', help='File subtype'),
    #
    # Console and UI settings
    #
    quiet: bool = Option(
        RECS.quiet, '-q', '--quiet', help='If true, do not display live updates'
    ),
    retain: bool = Option(
        RECS.retain, '-r', '--retain', help='Retain rich display on shutdown'
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
    infinite_length: bool = Option(
        RECS.infinite_length,
        help='If true, ignore file size limits (4G on .wav, 2G on .aiff)',
    ),
    longest_file_time: str = Option(
        RECS.longest_file_time, help='Longest amount of time per file: 0 means infinite'
    ),
    noise_floor: float = Option(
        RECS.noise_floor, '-o', '--noise-floor', help='The noise floor in decibels'
    ),
    silence_after_end: float = Option(
        RECS.silence_after_end,
        '-c',
        '--silence-after-end',
        help='Silence after the end, in seconds',
    ),
    silence_before_start: float = Option(
        RECS.silence_before_start,
        '-b',
        '--silence-before-start',
        help='Silence before the start, in seconds',
    ),
    stop_after_silence: float = Option(
        RECS.stop_after_silence,
        '--stop-after-silence',
        help='Stop recs after silence',
    ),
    total_run_time: float = Option(
        RECS.total_run_time,
        '-t',
        '--total-run-time',
        help='How many seconds to record? 0 means forever',
    ),
) -> None:
    Cfg(**locals()).run()


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
