import string
import sys
from pathlib import Path

import click
import dtyper
from typer import Argument, rich_utils

from . import RecsError, pyproject
from .cfg import Cfg
from .cfg_raw import CfgRaw

rich_utils.STYLE_METAVAR = 'dim yellow'
INTRO = f"""
  {pyproject.message()}

============================================="""
LINES = (
    INTRO,
    'Why should there be a record button at all?',
    'I wanted to digitize a huge number of cassettes and LPs, so I wanted a '
    + 'program that ran in the background and recorded everything except quiet.',
    'Nothing like that existed so I wrote it.  Free, open-source, configurable.',
    'Full documentation here: https://github.com/rec/recs',
    '',
)
HELP = '\n\n\n\n'.join(LINES)
# Three blank lines seems to force Typer to format correctly

app = dtyper.Typer(
    add_completion=False,
    context_settings={'help_option_names': ['--help', '-h']},
)
_SINGLES: set[str] = set()

RECS = CfgRaw()
# Reading configs and environment variables would go here


def Option(default, *a, **ka) -> dtyper.Option:
    _SINGLES.update(i[1] for i in a if len(i) == 2)
    return dtyper.Option(default, *a, **ka)


@app.command(help=HELP)
def recs(
    #
    # Directory settings
    #
    path: Path = Argument(
        RECS.path, help='Path to the parent directory to create audio files in'
    ),
    subdirectory: list[str] = Option(
        RECS.subdirectory,
        '-s',
        '--subdirectory',
        help='Organize files into subdirectories by channel, device or time.',
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
    list_types: bool = Option(
        RECS.list_types, help='List all subtypes for each format'
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
    # Audio file data
    #
    format: str = Option(RECS.format, '-f', '--format', help='Audio format'),
    metadata: list[str] = Option(
        RECS.metadata, '-m', '--metadata', help='Metadata fields to add to output files'
    ),
    sdtype: str = Option(
        RECS.sdtype, '-d', '--sdtype', help='Type of sounddevice numbers'
    ),
    subtype: str = Option(RECS.subtype, '-u', '--subtype', help='File subtype'),
    #
    # Console and UI settings
    #
    silent: bool = Option(
        RECS.silent, '-q', '--silent', help='If true, do not display live updates'
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
    moving_average_time: float = Option(
        RECS.moving_average_time, help='How long to average the volume display over'
    ),
    noise_floor: float = Option(
        RECS.noise_floor, '-o', '--noise-floor', help='The noise floor in decibels'
    ),
    shortest_file_time: str = Option(
        RECS.shortest_file_time, help='Shortest amount of time per file'
    ),
    quiet_after_end: float = Option(
        RECS.quiet_after_end,
        '-c',
        '--quiet-after-end',
        help='Quiet after the end, in seconds',
    ),
    quiet_before_start: float = Option(
        RECS.quiet_before_start,
        '-b',
        '--quiet-before-start',
        help='Quiet before the start, in seconds',
    ),
    stop_after_quiet: float = Option(
        RECS.stop_after_quiet,
        '--stop-after-quiet',
        help='Stop recs after quiet',
    ),
    total_run_time: float = Option(
        RECS.total_run_time,
        '-t',
        '--total-run-time',
        help='How many seconds to record? 0 means forever',
    ),
) -> None:  # pragma: no cover: This is tested in a subprocess.
    cfg = Cfg(**locals())

    from . import run

    run.run(cfg)


_USED_SINGLES = ''.join(sorted(_SINGLES))
_UNUSED_SINGLES = ''.join(sorted(set(string.ascii_lowercase) - set(_SINGLES)))

assert _USED_SINGLES == 'abcdefimnoqrstuv', _USED_SINGLES
assert _UNUSED_SINGLES == 'ghjklpwxyz', _UNUSED_SINGLES


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
