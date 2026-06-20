import typing as t
from pathlib import Path

import tyro
from tyro.constructors import PrimitiveConstructorSpec

from recs.base import pyproject, times, types
from recs.base.prefix_dict import PrefixDict
from recs.base.type_conversions import FORMATS, SDTYPES, SUBTYPES

from . import cfg

INTRO = f"""  {pyproject.message()}
============================================="""
LINES = (
    INTRO,
    'Why should there be a record button at all?',
    'I wanted to digitize a huge number of cassettes and LPs, so I wanted a '
    + 'program that ran in the background and recorded everything except quiet.',
    'Nothing like that existed so I wrote it.  Free, open-source, configurable.',
    'Full documentation here: https://github.com/rec/recs',
)
HELP = '\n\n'.join(LINES)

RECS = cfg.Cfg.raw_defaults()
# Reading configs and environment variables would go here

_T = t.TypeVar('_T')


def _prefix_spec(
    values: PrefixDict[_T], metavar: str
) -> PrimitiveConstructorSpec[_T]:
    def parse(args: list[str]) -> _T:
        try:
            return values[args[0]]
        except KeyError:
            raise ValueError(f'Cannot understand {metavar}="{args[0]}"') from None

    return PrimitiveConstructorSpec(
        nargs=1,
        metavar=metavar,
        instance_from_str=parse,
        is_instance=lambda value: value in values.values(),
        str_from_instance=lambda value: [str(value)],
    )


FORMAT_SPEC = _prefix_spec(FORMATS, 'AUDIO FORMAT')
SDTYPE_SPEC = _prefix_spec(SDTYPES, 'NUMERIC TYPE')
SUBTYPE_SPEC = _prefix_spec(SUBTYPES, 'AUDIO SUBTYPE')
TIME_SPEC = PrimitiveConstructorSpec[float](
    nargs=1,
    metavar='TIME',
    instance_from_str=lambda args: times.to_time(args[0]),
    is_instance=lambda value: isinstance(value, (int, float)),
    str_from_instance=lambda value: [str(value)],
)


def recs(
    files: t.Annotated[
        list[str],
        tyro.conf.Positional,
        tyro.conf.arg(
            default=RECS.files,
            help='One or more files to split for silence',
        ),
    ],
    output_directory: t.Annotated[
        str,
        tyro.conf.arg(
            aliases=('-o',),
            default=RECS.output_directory,
            help='Path or output_directory pattern for recorded file locations',
        ),
    ],
    short_file_names: t.Annotated[
        bool,
        tyro.conf.arg(
            default=RECS.short_file_names,
            help='Omit the device from generated names when there is only one',
        ),
    ],
    calibrate: t.Annotated[
        bool,
        tyro.conf.arg(
            default=RECS.calibrate,
            help='Detect and print noise levels, do not record',
        ),
    ],
    dry_run: t.Annotated[
        bool,
        tyro.conf.arg(
            aliases=('-n',),
            default=RECS.dry_run,
            help='Display levels only, do not record',
        ),
    ],
    verbose: t.Annotated[
        bool,
        tyro.conf.arg(
            aliases=('-v',), default=RECS.verbose, help='Print more stuff'
        ),
    ],
    info: t.Annotated[
        bool,
        tyro.conf.arg(default=RECS.info, help='Display device info as JSON'),
    ],
    list_types: t.Annotated[
        bool,
        tyro.conf.arg(
            default=RECS.list_types,
            help='List all subtypes for each format as JSON',
        ),
    ],
    alias: t.Annotated[
        tyro.conf.UseAppendAction[list[str]],
        tyro.conf.arg(
            aliases=('-a',),
            default=RECS.alias,
            help='Set aliases for devices or channels',
        ),
    ],
    devices: t.Annotated[
        Path,
        tyro.conf.arg(
            default=RECS.devices,
            help='A path to a JSON file with device definitions',
        ),
    ],
    exclude: t.Annotated[
        tyro.conf.UseAppendAction[list[str]],
        tyro.conf.arg(
            aliases=('-e',),
            default=RECS.exclude,
            help='Exclude devices or channels',
        ),
    ],
    include: t.Annotated[
        tyro.conf.UseAppendAction[list[str]],
        tyro.conf.arg(
            aliases=('-i',),
            default=RECS.include,
            help='Only include these devices or channels',
        ),
    ],
    formats: t.Annotated[
        tyro.conf.UseAppendAction[list[t.Annotated[types.Format, FORMAT_SPEC]]],
        tyro.conf.arg(
            aliases=('-f',), default=RECS.formats, help='Audio file formats'
        ),
    ],
    metadata: t.Annotated[
        tyro.conf.UseAppendAction[list[str]],
        tyro.conf.arg(
            aliases=('-m',),
            default=RECS.metadata,
            help='Metadata fields to add to output files',
        ),
    ],
    sdtype: t.Annotated[
        t.Annotated[types.SdType, SDTYPE_SPEC] | None,
        tyro.conf.arg(
            aliases=('-d',),
            default=RECS.sdtype,
            help='Integer or float number type for recording',
        ),
    ],
    subtype: t.Annotated[
        t.Annotated[types.Subtype, SUBTYPE_SPEC] | None,
        tyro.conf.arg(
            aliases=('-u',),
            default=RECS.subtype,
            help='Audio file subtype',
        ),
    ],
    clear_terminal: t.Annotated[
        bool,
        tyro.conf.arg(
            aliases=('-r',),
            default=RECS.clear_terminal,
            help='Clear display on shutdown',
        ),
    ],
    silent: t.Annotated[
        bool,
        tyro.conf.arg(
            aliases=('-s',),
            default=RECS.silent,
            help='Do not display live updates',
        ),
    ],
    sleep_time_device: t.Annotated[
        float,
        TIME_SPEC,
        tyro.conf.arg(
            default=RECS.sleep_time_device,
            help='How long to sleep between checking device',
        ),
    ],
    ui_refresh_rate: t.Annotated[
        float,
        tyro.conf.arg(
            default=RECS.ui_refresh_rate,
            help='How many UI refreshes per second',
        ),
    ],
    band_mode: t.Annotated[
        bool,
        tyro.conf.arg(
            aliases=('-B',),
            default=RECS.band_mode,
            help='Band mode: any track starting starts them all',
        ),
    ],
    infinite_length: t.Annotated[
        bool,
        tyro.conf.arg(
            default=RECS.infinite_length,
            help='Ignore file size limit: 4G on .wav',
        ),
    ],
    longest_file_time: t.Annotated[
        float,
        TIME_SPEC,
        tyro.conf.arg(
            default=RECS.longest_file_time,
            help='Longest amount of time per file: 0 means infinite',
        ),
    ],
    moving_average_time: t.Annotated[
        float,
        TIME_SPEC,
        tyro.conf.arg(
            default=RECS.moving_average_time,
            help='How long to average the volume display over',
        ),
    ],
    noise_floor: t.Annotated[
        float,
        tyro.conf.arg(
            aliases=('-z',),
            default=RECS.noise_floor,
            help='The noise floor in decibels',
        ),
    ],
    record_everything: t.Annotated[
        bool,
        tyro.conf.arg(
            aliases=('-R',),
            default=RECS.record_everything,
            help='Start immediately, record everything until end',
        ),
    ],
    shortest_file_time: t.Annotated[
        float,
        TIME_SPEC,
        tyro.conf.arg(
            default=RECS.shortest_file_time,
            help='Files shorter than this duration get deleted',
        ),
    ],
    quiet_after_end: t.Annotated[
        float,
        TIME_SPEC,
        tyro.conf.arg(
            aliases=('-c',),
            default=RECS.quiet_after_end,
            help='How much quiet after the end',
        ),
    ],
    quiet_before_start: t.Annotated[
        float,
        TIME_SPEC,
        tyro.conf.arg(
            aliases=('-b',),
            default=RECS.quiet_before_start,
            help='How much quiet before a recording',
        ),
    ],
    stop_after_quiet: t.Annotated[
        float,
        TIME_SPEC,
        tyro.conf.arg(
            default=RECS.stop_after_quiet,
            help='How much quiet before stopping a recording',
        ),
    ],
    total_run_time: t.Annotated[
        float,
        TIME_SPEC,
        tyro.conf.arg(
            aliases=('-t',),
            default=RECS.total_run_time,
            help='How many seconds to record? 0 means forever',
        ),
    ],
) -> None:
    c = cfg.Cfg(**locals())

    from . import run_cli

    run_cli.run_cli(c)
