from pathlib import Path
from typing import Annotated, TypeVar

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

_T = TypeVar('_T')


def _prefix_spec(values: PrefixDict[_T], metavar: str) -> PrimitiveConstructorSpec[_T]:
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
RECORD_KEYS = PrefixDict({value: value for value in types.RecordKeys})
RECORD_KEYS_SPEC = _prefix_spec(RECORD_KEYS, 'KEY RECORDING MODE')
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
    files: Annotated[
        list[str],
        tyro.conf.Positional,
        tyro.conf.arg(
            default=RECS.directory.files,
            help='One or more files to split for silence',
        ),
    ],
    output_directory: Annotated[
        str,
        tyro.conf.arg(
            aliases=('-o',),
            default=RECS.directory.output_directory,
            help='Path or output_directory pattern for recorded file locations',
        ),
    ],
    short_file_names: Annotated[
        bool,
        tyro.conf.arg(
            default=RECS.directory.short_file_names,
            help='Omit the device from generated names when there is only one',
        ),
    ],
    calibrate: Annotated[
        bool,
        tyro.conf.arg(
            default=RECS.general.calibrate,
            help='Detect and print noise levels, do not record',
        ),
    ],
    default_record_directory: Annotated[
        str,
        tyro.conf.arg(
            default=RECS.general.default_record_directory,
            help='Directory name to use for automatic daemon recordings',
        ),
    ],
    dry_run: Annotated[
        bool,
        tyro.conf.arg(
            aliases=('-n',),
            default=RECS.general.dry_run,
            help='Display levels only, do not record',
        ),
    ],
    verbose: Annotated[
        bool,
        tyro.conf.arg(
            aliases=('-v',), default=RECS.general.verbose, help='Print more stuff'
        ),
    ],
    info: Annotated[
        bool,
        tyro.conf.arg(default=RECS.general.info, help='Display device info as JSON'),
    ],
    list_types: Annotated[
        bool,
        tyro.conf.arg(
            default=RECS.general.list_types,
            help='List all subtypes for each format as JSON',
        ),
    ],
    silence_preview: Annotated[
        bool,
        tyro.conf.arg(
            default=RECS.general.silence_preview,
            help='Show live silence measurements and suggested recording thresholds',
        ),
    ],
    save_settings: Annotated[
        bool | None,
        tyro.conf.arg(
            default=RECS.general.save_settings,
            help='Save mutable API settings for the next recording run',
        ),
    ],
    alias: Annotated[
        tyro.conf.UseAppendAction[list[str]],
        tyro.conf.arg(
            aliases=('-a',),
            default=RECS.device.alias,
            help='Set aliases for devices or channels',
        ),
    ],
    devices: Annotated[
        Path,
        tyro.conf.arg(
            default=RECS.device.devices,
            help='A path to a JSON file with device definitions',
        ),
    ],
    profiles: Annotated[
        Path,
        tyro.conf.arg(
            default=RECS.device.profiles,
            help='A JSON file with per-device default profiles',
        ),
    ],
    exclude: Annotated[
        tyro.conf.UseAppendAction[list[str]],
        tyro.conf.arg(
            aliases=('-e',),
            default=RECS.selection.exclude,
            help='Exclude devices or channels',
        ),
    ],
    include: Annotated[
        tyro.conf.UseAppendAction[list[str]],
        tyro.conf.arg(
            aliases=('-i',),
            default=RECS.selection.include,
            help='Only include these devices or channels',
        ),
    ],
    formats: Annotated[
        tyro.conf.UseAppendAction[list[Annotated[types.Format, FORMAT_SPEC]]],
        tyro.conf.arg(
            aliases=('-f',), default=RECS.audio.formats, help='Audio file formats'
        ),
    ],
    metadata: Annotated[
        tyro.conf.UseAppendAction[list[str]],
        tyro.conf.arg(
            aliases=('-m',),
            default=RECS.audio.metadata,
            help='Metadata fields to add to output files',
        ),
    ],
    sdtype: Annotated[
        Annotated[types.SdType, SDTYPE_SPEC] | None,
        tyro.conf.arg(
            aliases=('-d',),
            default=RECS.audio.sdtype,
            help='Integer or float number type for recording',
        ),
    ],
    subtype: Annotated[
        Annotated[types.Subtype, SUBTYPE_SPEC] | None,
        tyro.conf.arg(
            aliases=('-u',),
            default=RECS.audio.subtype,
            help='Audio file subtype',
        ),
    ],
    clear_terminal: Annotated[
        bool,
        tyro.conf.arg(
            aliases=('-r',),
            default=RECS.console.clear_terminal,
            help='Clear display on shutdown',
        ),
    ],
    gui: Annotated[
        bool,
        tyro.conf.arg(
            default=RECS.console.gui,
            help='Display live updates in a PySide6 window',
        ),
    ],
    open_output_folder: Annotated[
        bool,
        tyro.conf.arg(
            default=RECS.console.open_output_folder,
            help='Open the output folder when recording finishes',
        ),
    ],
    remote: Annotated[
        bool,
        tyro.conf.arg(
            default=RECS.console.remote,
            help='Connect to an already-running recs daemon instead of recording',
        ),
    ],
    silent: Annotated[
        bool,
        tyro.conf.arg(
            aliases=('-s',),
            default=RECS.console.silent,
            help='Do not display live updates',
        ),
    ],
    sleep_time_device: Annotated[
        float,
        TIME_SPEC,
        tyro.conf.arg(
            default=RECS.console.sleep_time_device,
            help='How long to sleep between checking device',
        ),
    ],
    ui_refresh_rate: Annotated[
        float,
        tyro.conf.arg(
            default=RECS.console.ui_refresh_rate,
            help='How many UI refreshes per second',
        ),
    ],
    key_label: Annotated[
        tyro.conf.UseAppendAction[list[str]],
        tyro.conf.arg(
            default=RECS.keys.key_label,
            help='Add a manifest label for a key, for example g=guitar too soft',
        ),
    ],
    record_keys: Annotated[
        Annotated[types.RecordKeys, RECORD_KEYS_SPEC] | None,
        tyro.conf.arg(
            default=RECS.keys.record_keys,
            help='Record keys in the session manifest: none, press, or all',
        ),
    ],
    record_key_all_apps: Annotated[
        bool | None,
        tyro.conf.arg(
            default=RECS.keys.record_key_all_apps,
            help='Record key events from all applications when supported',
        ),
    ],
    audio_buffer_seconds: Annotated[
        float,
        TIME_SPEC,
        tyro.conf.arg(
            default=RECS.recording.audio_buffer_seconds,
            help='How much captured audio to buffer while disk writes catch up',
        ),
    ],
    band_mode: Annotated[
        bool,
        tyro.conf.arg(
            aliases=('-B',),
            default=RECS.recording.band_mode,
            help='Band mode: any track starting starts them all',
        ),
    ],
    buffer_status_period: Annotated[
        float,
        TIME_SPEC,
        tyro.conf.arg(
            default=RECS.recording.buffer_status_period,
            help='How often to repeat buffer pressure warnings',
        ),
    ],
    buffer_warning_fraction: Annotated[
        float,
        tyro.conf.arg(
            default=RECS.recording.buffer_warning_fraction,
            help='Warn when the audio buffer reaches this fraction full',
        ),
    ],
    channel_noise_floors: Annotated[
        dict[str, dict[str, float | None]],
        tyro.conf.arg(
            default=RECS.recording.channel_noise_floors,
            help='Per-device mono or stereo track noise floor overrides',
        ),
    ],
    infinite_length: Annotated[
        bool,
        tyro.conf.arg(
            default=RECS.recording.infinite_length,
            help='Ignore file size limit: 4G on .wav',
        ),
    ],
    longest_file_time: Annotated[
        float,
        TIME_SPEC,
        tyro.conf.arg(
            default=RECS.recording.longest_file_time,
            help='Longest amount of time per file: 0 means infinite',
        ),
    ],
    minimum_free_space: Annotated[
        int,
        tyro.conf.arg(
            default=RECS.recording.minimum_free_space,
            help='Absolute disk-space reserve used with the emergency threshold',
        ),
    ],
    disk_alert_thresholds: Annotated[
        tyro.conf.UseAppendAction[list[str]],
        tyro.conf.arg(
            default=RECS.recording.disk_alert_thresholds,
            help='Free-space alerts, such as 30m or 500MB',
        ),
    ],
    disk_removable_emergency: Annotated[
        tyro.conf.UseAppendAction[list[str]],
        tyro.conf.arg(
            default=RECS.recording.disk_removable_emergency,
            help='Emergency reserve on removable disks',
        ),
    ],
    disk_system_emergency: Annotated[
        tyro.conf.UseAppendAction[list[str]],
        tyro.conf.arg(
            default=RECS.recording.disk_system_emergency,
            help='Emergency reserve on the system disk',
        ),
    ],
    disk_removable_pause: Annotated[
        tyro.conf.UseAppendAction[list[str]],
        tyro.conf.arg(
            default=RECS.recording.disk_removable_pause,
            help='Pause reserve on removable disks',
        ),
    ],
    disk_system_pause: Annotated[
        tyro.conf.UseAppendAction[list[str]],
        tyro.conf.arg(
            default=RECS.recording.disk_system_pause,
            help='Pause reserve on the system disk',
        ),
    ],
    disk_poll_seconds: Annotated[
        float,
        TIME_SPEC,
        tyro.conf.arg(
            default=RECS.recording.disk_poll_seconds,
            help='How often to check recording disk space',
        ),
    ],
    disk_auto_switch: Annotated[
        bool,
        tyro.conf.arg(
            default=RECS.recording.disk_auto_switch,
            help='Switch to a better removable disk after a disk-space alert',
        ),
    ],
    moving_average_time: Annotated[
        float,
        TIME_SPEC,
        tyro.conf.arg(
            default=RECS.recording.moving_average_time,
            help='How long to average the volume display over',
        ),
    ],
    noise_floor: Annotated[
        float,
        tyro.conf.arg(
            aliases=('-z',),
            default=RECS.recording.noise_floor,
            help='The noise floor in decibels',
        ),
    ],
    preview_headroom: Annotated[
        float,
        tyro.conf.arg(
            default=RECS.recording.preview_headroom,
            help='Headroom in decibels to add to silence preview measurements',
        ),
    ],
    record_everything: Annotated[
        bool,
        tyro.conf.arg(
            aliases=('-R',),
            default=RECS.recording.record_everything,
            help='Start immediately, record everything until end',
        ),
    ],
    shortest_file_time: Annotated[
        float,
        TIME_SPEC,
        tyro.conf.arg(
            default=RECS.recording.shortest_file_time,
            help='Files shorter than this duration get deleted',
        ),
    ],
    quiet_after_end: Annotated[
        float,
        TIME_SPEC,
        tyro.conf.arg(
            aliases=('-c',),
            default=RECS.recording.quiet_after_end,
            help='How much quiet after the end',
        ),
    ],
    quiet_before_start: Annotated[
        float,
        TIME_SPEC,
        tyro.conf.arg(
            aliases=('-b',),
            default=RECS.recording.quiet_before_start,
            help='How much quiet before a recording',
        ),
    ],
    stop_after_quiet: Annotated[
        float,
        TIME_SPEC,
        tyro.conf.arg(
            default=RECS.recording.stop_after_quiet,
            help='How much quiet before stopping a recording',
        ),
    ],
    total_run_time: Annotated[
        float,
        TIME_SPEC,
        tyro.conf.arg(
            aliases=('-t',),
            default=RECS.recording.total_run_time,
            help='How many seconds to record? 0 means forever',
        ),
    ],
) -> None:
    c = cfg.Cfg(**locals())

    from . import run_cli

    run_cli.run_cli(c)
