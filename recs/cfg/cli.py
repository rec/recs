import string
from pathlib import Path

import dtyper
from typer import Argument, rich_utils

from recs.base import types
from recs.base.cfg_raw import CfgRaw

from . import app, cfg

rich_utils.STYLE_METAVAR = 'dim yellow'
# Three blank lines seems to force Typer to format correctly

_SINGLES: set[str] = set()

RECS = CfgRaw()
# Reading configs and environment variables would go here


def Option(default, *a, **ka) -> dtyper.Option:
    _SINGLES.update(i[1] for i in a if len(i) == 2)
    return dtyper.Option(default, *a, **ka)


GENERAL_PANEL = 'Options'  # 'General Settings'
SUBCOMMANDS_PANEL = 'Subcommands'
NAMES_PANEL = 'Selecting and Naming Devices and Channels'
FILE_PANEL = 'Audio File Format Settings'
CONSOLE_PANEL = 'Console and UI Settings'
RECORD_PANEL = 'Record Settings'


@app.app.command(help=app.HELP)
def recs(
    #
    # Directory settings
    #
    path: str = Argument(
        RECS.path, help='Path or path pattern for recorded file locations'
    ),
    #
    # General
    #
    calibrate: bool = Option(
        RECS.calibrate,
        '--calibrate',
        help='Detect and print noise levels, do not record',
        rich_help_panel=GENERAL_PANEL,
    ),
    dry_run: bool = Option(
        RECS.dry_run,
        '-n',
        '--dry-run',
        help='Display levels only, do not record',
        rich_help_panel=GENERAL_PANEL,
    ),
    verbose: bool = Option(
        RECS.verbose,
        '-v',
        '--verbose',
        help='Print more stuff - currently does nothing',
        rich_help_panel=GENERAL_PANEL,
    ),
    #
    # Subcommands
    #
    info: bool = Option(
        RECS.info,
        '--info',
        help='Display device info as JSON',
        rich_help_panel=SUBCOMMANDS_PANEL,
    ),
    list_types: bool = Option(
        RECS.list_types,
        '--list-types',
        help='List all subtypes for each format as JSON',
        rich_help_panel=SUBCOMMANDS_PANEL,
    ),
    #
    # Names
    #
    alias: list[str] = Option(
        RECS.alias,
        '-a',
        '--alias',
        click_type=app.AliasParam(),
        help='Set aliases for devices or channels',
        rich_help_panel=NAMES_PANEL,
    ),
    devices: Path = Option(
        RECS.devices,
        help='A path to a JSON file with device definitions',
        rich_help_panel=NAMES_PANEL,
    ),
    exclude: list[str] = Option(
        RECS.exclude,
        '-e',
        '--exclude',
        help='Exclude devices or channels',
        rich_help_panel=NAMES_PANEL,
    ),
    include: list[str] = Option(
        RECS.include,
        '-i',
        '--include',
        help='Only include these devices or channels',
        rich_help_panel=NAMES_PANEL,
    ),
    #
    # File
    #
    format: types.Format = Option(
        RECS.format,
        '-f',
        '--format',
        click_type=app.FormatParam(),
        help='Audio file format',
        rich_help_panel=FILE_PANEL,
    ),
    metadata: list[str] = Option(
        RECS.metadata,
        '-m',
        '--metadata',
        click_type=app.MetadataParam(),
        help='Metadata fields to add to output files',
        rich_help_panel=FILE_PANEL,
    ),
    sdtype: types.SdType
    | None = Option(
        RECS.sdtype,
        '-d',
        '--sdtype',
        click_type=app.SdTypeParam(),
        help='Integer or float number type for recording',
        rich_help_panel=FILE_PANEL,
    ),
    subtype: types.Subtype
    | None = Option(
        RECS.subtype,
        '-u',
        '--subtype',
        click_type=app.SubtypeParam(),
        help='Audio file subtype',
        rich_help_panel=FILE_PANEL,
    ),
    #
    # Console
    #
    clear: bool = Option(
        RECS.clear,
        '-r',
        '--clear',
        help='Clear display on shutdown',
        rich_help_panel=CONSOLE_PANEL,
    ),
    silent: bool = Option(
        RECS.silent,
        '-s',
        '--silent',
        help='Do not display live updates',
        rich_help_panel=CONSOLE_PANEL,
    ),
    sleep_time_device: str = Option(
        RECS.sleep_time_device,
        '--sleep-time-device',
        click_type=app.TimeParam(),
        help='How long to sleep between checking device',
        rich_help_panel=CONSOLE_PANEL,
    ),
    ui_refresh_rate: float = Option(
        RECS.ui_refresh_rate,
        '--ui-refresh-rate',
        help='How many UI refreshes per second',
        rich_help_panel=CONSOLE_PANEL,
    ),
    #
    # Record
    #
    infinite_length: bool = Option(
        RECS.infinite_length,
        '--infinite-length',
        help='Ignore file size limits (4G on .wav, 2G on .aiff)',
        rich_help_panel=RECORD_PANEL,
    ),
    longest_file_time: str = Option(
        RECS.longest_file_time,
        click_type=app.TimeParam(),
        help='Longest amount of time per file: 0 means infinite',
        rich_help_panel=RECORD_PANEL,
    ),
    moving_average_time: str = Option(
        RECS.moving_average_time,
        click_type=app.TimeParam(),
        help='How long to average the volume display over',
        rich_help_panel=RECORD_PANEL,
    ),
    noise_floor: float = Option(
        RECS.noise_floor,
        '-o',
        '--noise-floor',
        help='The noise floor in decibels',
        rich_help_panel=RECORD_PANEL,
    ),
    shortest_file_time: str = Option(
        RECS.shortest_file_time,
        click_type=app.TimeParam(),
        help='Shortest amount of time per file',
        rich_help_panel=RECORD_PANEL,
    ),
    quiet_after_end: str = Option(
        RECS.quiet_after_end,
        '-c',
        '--quiet-after-end',
        click_type=app.TimeParam(),
        help='How much quiet after the end',
        rich_help_panel=RECORD_PANEL,
    ),
    quiet_before_start: str = Option(
        RECS.quiet_before_start,
        '-b',
        '--quiet-before-start',
        click_type=app.TimeParam(),
        help='How much quiet before a recording',
        rich_help_panel=RECORD_PANEL,
    ),
    stop_after_quiet: str = Option(
        RECS.stop_after_quiet,
        '--stop-after-quiet',
        click_type=app.TimeParam(),
        help='How much quiet before stopping a recording',
        rich_help_panel=RECORD_PANEL,
    ),
    total_run_time: str = Option(
        RECS.total_run_time,
        '-t',
        '--total-run-time',
        click_type=app.TimeParam(),
        help='How many seconds to record? 0 means forever',
        rich_help_panel=RECORD_PANEL,
    ),
) -> None:
    c = cfg.Cfg(**locals())

    from . import run_cli

    run_cli.run_cli(c)


_USED_SINGLES = ''.join(sorted(_SINGLES))
_UNUSED_SINGLES = ''.join(sorted(set(string.ascii_lowercase) - set(_SINGLES)))

assert _USED_SINGLES == 'abcdefimnorstuv', _USED_SINGLES
assert _UNUSED_SINGLES == 'ghjklpqwxyz', _UNUSED_SINGLES
