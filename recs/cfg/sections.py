import json
import warnings
from functools import cached_property
from pathlib import Path
from typing import Annotated, Self

import soundfile
import tyro
from pydantic import BaseModel, Field, field_validator, model_validator
from reccy.configuration import units
from ufor.encoding import Format, Subtype

from recs.base.type_conversions import SDTYPE_TO_SUBTYPE, SUBTYPE_TO_SDTYPE
from recs.base.types import SDTYPE, MidiTiming, Mutable, RecordKeys, SdType

from . import cli_metadata, disk_threshold


class Directory(BaseModel):
    # See ./cli.py for full help
    #
    # Directory settings
    #
    files: Annotated[
        list[Path],
        tyro.conf.Positional,
        tyro.conf.arg(help='One or more files to split for silence'),
    ] = Field(default_factory=list)

    output_directory: Annotated[
        str,
        Mutable,
        tyro.conf.arg(
            aliases=('-o',),
            help='Path or output_directory pattern for recorded file locations',
        ),
    ] = ''

    short_file_names: Annotated[
        bool,
        Mutable,
        tyro.conf.arg(
            help='Omit the device from generated names when there is only one'
        ),
    ] = True

    @field_validator('files')
    @classmethod
    def validate_files_exist(cls, files: list[Path]) -> list[Path]:
        if missing := [path for path in files if not path.exists()]:
            suffix = 's' * (len(missing) != 1)
            names = ', '.join(str(path) for path in missing)
            raise ValueError(f'Non-existent file{suffix}: {names}')
        return files


class General(BaseModel):
    #
    # General purpose settings
    #
    calibrate: Annotated[
        bool, tyro.conf.arg(help='Detect and print noise levels, do not record')
    ] = False

    default_record_directory: Annotated[
        str,
        tyro.conf.arg(help='Directory name to use for automatic daemon recordings'),
    ] = 'recs'

    dry_run: Annotated[
        bool,
        tyro.conf.arg(aliases=('-n',), help='Display levels only, do not record'),
    ] = False

    verbose: Annotated[
        bool, tyro.conf.arg(aliases=('-v',), help='Print more stuff')
    ] = False

    info: Annotated[bool, tyro.conf.arg(help='Display device info as JSON')] = False

    list_types: Annotated[
        bool, tyro.conf.arg(help='List all subtypes for each format as JSON')
    ] = False

    silence_preview: Annotated[
        bool,
        tyro.conf.arg(
            help='Show live silence measurements and suggested recording thresholds'
        ),
    ] = False

    save_settings: Annotated[
        bool | None,
        tyro.conf.arg(help='Save mutable API settings for the next recording run'),
    ] = None

    @property
    def writes_files(self) -> bool:
        return not (self.dry_run or self.calibrate or self.silence_preview)


class Device(BaseModel):
    #
    # Aliases for input devices or channels
    #
    alias: Annotated[
        tyro.conf.UseAppendAction[list[str]],
        tyro.conf.arg(aliases=('-a',), help='Set aliases for devices or channels'),
    ] = Field(default_factory=list)

    devices: Annotated[
        Path, tyro.conf.arg(help='A path to a JSON file with device definitions')
    ] = Path()

    profiles: Annotated[
        Path,
        Mutable,
        tyro.conf.arg(help='Per-device JSON defaults, not a named saved setup'),
    ] = Path()

    @field_validator('devices')
    @classmethod
    def validate_devices_file(cls, devices: Path) -> Path:
        if not devices.name:
            return devices
        if not devices.exists():
            raise ValueError(f'{devices} does not exist')
        if not json.loads(devices.read_text()):
            raise ValueError(f'{devices} contains no devices')
        return devices

    @field_validator('profiles')
    @classmethod
    def validate_profiles_file(cls, profiles: Path) -> Path:
        return profiles


class Selection(BaseModel):
    #
    # Exclude or include devices or channels
    #
    exclude: Annotated[
        tyro.conf.UseAppendAction[list[str]],
        tyro.conf.arg(aliases=('-e',), help='Exclude devices or channels'),
    ] = Field(default_factory=list)

    include: Annotated[
        tyro.conf.UseAppendAction[list[str]],
        tyro.conf.arg(aliases=('-i',), help='Only include these devices or channels'),
    ] = Field(default_factory=list)


class Audio(BaseModel):
    #
    # Audio file format and subtype
    #
    formats: Annotated[
        tyro.conf.UseAppendAction[list[Annotated[Format, cli_metadata.FORMAT_SPEC]]],
        tyro.conf.arg(aliases=('-f',), help='Audio file formats'),
    ] = Field(default_factory=list)

    metadata: Annotated[
        tyro.conf.UseAppendAction[list[str]],
        Mutable,
        tyro.conf.arg(aliases=('-m',), help='Metadata fields to add to output files'),
    ] = Field(default_factory=list)

    sdtype: Annotated[
        Annotated[SdType, cli_metadata.SDTYPE_SPEC] | None,
        tyro.conf.arg(
            aliases=('-d',), help='Integer or float number type for recording'
        ),
    ] = None

    subtype: Annotated[
        Annotated[Subtype, cli_metadata.SUBTYPE_SPEC] | None,
        tyro.conf.arg(aliases=('-u',), help='Audio file subtype'),
    ] = None

    @model_validator(mode='after')
    def configure_audio_types(self) -> Self:
        fields_set = set(self.model_fields_set)
        # Tyro marks nested Pydantic defaults as set; restore raw CLI defaults.
        if fields_set == set(type(self).model_fields):
            if len(self.formats) > 1 and self.formats[0] == Format.flac:
                self.formats = self.formats[1:]
            if self.sdtype == SDTYPE and self.subtype is None:
                fields_set.remove('sdtype')
        self.formats = self.formats or [Format.flac]

        if self.subtype and not soundfile.check_format(self.formats[0], self.subtype):
            raise ValueError(f'{self.formats[0]} and {self.subtype} are incompatible')

        if self.subtype:
            pass
        elif not self.sdtype or 'sdtype' not in fields_set:
            self.subtype = None
        else:
            subtype = SDTYPE_TO_SUBTYPE[self.sdtype]

            if soundfile.check_format(self.formats[0], subtype):
                self.subtype = subtype
            else:
                self.subtype = None
                msg = f'formats={self.formats[0]:s}, sdtype={self.sdtype:s}'
                warnings.warn(f"Can't get subtype for {msg}", stacklevel=2)

        if self.sdtype and 'sdtype' in fields_set:
            pass
        elif self.subtype:
            self.sdtype = SUBTYPE_TO_SDTYPE.get(self.subtype, SDTYPE)
        else:
            self.sdtype = SDTYPE
        object.__setattr__(self, '__pydantic_fields_set__', fields_set)
        return self


class Midi(BaseModel):
    #
    # MIDI recording
    #
    record_midi: Annotated[
        bool,
        tyro.conf.arg(aliases=('--midi',), help='Record MIDI inputs'),
    ] = True

    midi_include: Annotated[
        tyro.conf.UseAppendAction[list[str]],
        tyro.conf.arg(help='Only record these MIDI input name prefixes'),
    ] = Field(default_factory=list)

    midi_exclude: Annotated[
        tyro.conf.UseAppendAction[list[str]],
        tyro.conf.arg(help='Exclude these MIDI input name prefixes'),
    ] = Field(default_factory=list)

    midi_timing: Annotated[
        MidiTiming,
        tyro.conf.arg(help='MIDI timing: system callback clock, or mido source deltas'),
    ] = MidiTiming.system


class Osc(BaseModel):
    #
    # OSC recording
    #
    osc_nodes: Annotated[
        Path,
        tyro.conf.arg(help='TOML file describing OSC nodes to record'),
    ] = Path()

    @field_validator('osc_nodes')
    @classmethod
    def validate_osc_nodes(cls, path: Path) -> Path:
        if path.name and not path.exists():
            raise ValueError(f'{path} does not exist')
        return path


class Console(BaseModel):
    #
    # Console and UI settings
    #
    clear_terminal: Annotated[
        bool, tyro.conf.arg(aliases=('-r',), help='Clear display on shutdown')
    ] = True

    gui: Annotated[
        bool, tyro.conf.arg(help='Display live updates in a PySide6 window')
    ] = False

    open_output_folder: Annotated[
        bool, tyro.conf.arg(help='Open the output folder when recording finishes')
    ] = False

    remote: Annotated[
        bool,
        tyro.conf.arg(
            help='Connect to an already-running recs daemon instead of recording'
        ),
    ] = False

    silent: Annotated[
        bool, tyro.conf.arg(aliases=('-s',), help='Do not display live updates')
    ] = False

    sleep_time_device: Annotated[
        units.Seconds,
        cli_metadata.TIME_SPEC,
        tyro.conf.arg(help='How long to sleep between checking device'),
    ] = 0.1

    ui_refresh_rate: Annotated[
        units.Hertz,
        cli_metadata.HERTZ_SPEC,
        tyro.conf.arg(help='How many UI refreshes per second'),
    ] = 10.0

    waveform_bucket_milliseconds: Annotated[
        units.WholeMilliseconds,
        cli_metadata.MILLISECONDS_SPEC,
        tyro.conf.arg(help='Milliseconds represented by each live waveform bucket'),
    ] = 20

    waveform_batch_milliseconds: Annotated[
        units.WholeMilliseconds,
        cli_metadata.MILLISECONDS_SPEC,
        tyro.conf.arg(help='Milliseconds represented by each live waveform batch'),
    ] = 100

    @field_validator('sleep_time_device', 'ui_refresh_rate')
    @classmethod
    def validate_positive(cls, value: float) -> float:
        if value <= 0:
            raise ValueError('must be positive')
        return value

    @field_validator('waveform_bucket_milliseconds', 'waveform_batch_milliseconds')
    @classmethod
    def validate_waveform_milliseconds(cls, value: int) -> int:
        if value <= 0:
            raise ValueError('must be positive')
        return value

    @model_validator(mode='after')
    def validate_waveform_batch(self) -> Self:
        if self.waveform_batch_milliseconds % self.waveform_bucket_milliseconds:
            raise ValueError(
                'waveform_batch_milliseconds must be a multiple of '
                'waveform_bucket_milliseconds'
            )
        return self


class Key(BaseModel):
    #
    # Keyboard event recording
    #
    key_label: Annotated[
        tyro.conf.UseAppendAction[list[str]],
        Mutable,
        tyro.conf.arg(
            help='Add a record label for a key, for example g=guitar too soft'
        ),
    ] = Field(default_factory=list)

    record_keys: Annotated[
        Annotated[RecordKeys, cli_metadata.RECORD_KEYS_SPEC] | None,
        tyro.conf.arg(help='Record keys in the session record: none, press, or all'),
    ] = None

    record_key_all_apps: Annotated[
        bool | None,
        tyro.conf.arg(
            help='Record key events from all applications; must be explicitly enabled'
        ),
    ] = None

    @field_validator('key_label')
    @classmethod
    def validate_key_label(cls, key_label: list[str]) -> list[str]:
        for entry in key_label:
            key, separator, label = entry.partition('=')
            if not separator or not key or not label:
                raise ValueError(f'key_label must look like key=label: {entry}')
        return key_label

    @cached_property
    def labels(self) -> dict[str, str]:
        labels: dict[str, str] = {}
        for entry in self.key_label:
            key, _, label = entry.partition('=')
            labels[key] = label
        return labels


class Recording(BaseModel):
    #
    # Settings relating to times
    #
    audio_buffer_seconds: Annotated[
        units.Seconds,
        cli_metadata.TIME_SPEC,
        tyro.conf.arg(
            help='Seconds of audio to buffer before dropping delayed callbacks'
        ),
    ] = 10.0

    memory_reserve_megabytes: Annotated[
        units.Megabytes,
        cli_metadata.MEGABYTES_SPEC,
        tyro.conf.arg(help='Free system memory to reserve while buffering audio'),
    ] = 200

    memory_check_period: Annotated[
        units.Seconds,
        cli_metadata.TIME_SPEC,
        tyro.conf.arg(help='How often to check available system memory'),
    ] = 2.0

    band_mode: Annotated[
        bool,
        Mutable,
        tyro.conf.arg(
            aliases=('-B',), help='Band mode: any track starting starts them all'
        ),
    ] = False

    channel_noise_floors: Annotated[
        dict[str, dict[str, float | None]],
        Mutable,
        tyro.conf.arg(help='Per-device mono or stereo track noise floor overrides'),
    ] = Field(default_factory=dict)

    infinite_length: Annotated[
        bool, tyro.conf.arg(help='Ignore file size limit: 4G on .wav')
    ] = False

    longest_file_time: Annotated[
        units.Seconds,
        Mutable,
        cli_metadata.TIME_SPEC,
        tyro.conf.arg(help='Longest amount of time per file: 0 means infinite'),
    ] = 0.0

    minimum_free_space: Annotated[
        units.Bytes,
        cli_metadata.BYTES_SPEC,
        Mutable,
        tyro.conf.arg(
            help='Absolute disk-space reserve used with the emergency threshold'
        ),
    ] = 0

    disk_alert_thresholds: Annotated[
        tyro.conf.UseAppendAction[list[str]],
        Mutable,
        tyro.conf.arg(help='Free-space alerts, such as 30m or 500MB'),
    ] = Field(default_factory=lambda: ['30m', '10m', '2m'], validate_default=True)

    disk_removable_emergency: Annotated[
        tyro.conf.UseAppendAction[list[str]],
        Mutable,
        tyro.conf.arg(help='Emergency reserve on removable disks'),
    ] = Field(default_factory=lambda: ['200MB', '30s'], validate_default=True)

    disk_system_emergency: Annotated[
        tyro.conf.UseAppendAction[list[str]],
        Mutable,
        tyro.conf.arg(help='Emergency reserve on the system disk'),
    ] = Field(default_factory=lambda: ['2GB', '2m'], validate_default=True)

    disk_removable_pause: Annotated[
        tyro.conf.UseAppendAction[list[str]],
        Mutable,
        tyro.conf.arg(help='Pause reserve on removable disks'),
    ] = Field(default_factory=lambda: ['200MB', '30s'], validate_default=True)

    disk_system_pause: Annotated[
        tyro.conf.UseAppendAction[list[str]],
        Mutable,
        tyro.conf.arg(help='Pause reserve on the system disk'),
    ] = Field(default_factory=lambda: ['2GB', '2m'], validate_default=True)

    disk_poll_seconds: Annotated[
        units.Seconds,
        Mutable,
        cli_metadata.TIME_SPEC,
        tyro.conf.arg(help='How often to check recording disk space'),
    ] = 1.0

    card_replace_poll_seconds: Annotated[
        units.Seconds,
        Mutable,
        cli_metadata.TIME_SPEC,
        tyro.conf.arg(help='How often to poll for a replacement recording card'),
    ] = 1.0

    card_replace_timeout_seconds: Annotated[
        units.Seconds,
        Mutable,
        cli_metadata.TIME_SPEC,
        tyro.conf.arg(help='How long to wait for a replacement recording card'),
    ] = 300.0

    disk_auto_switch: Annotated[
        bool,
        Mutable,
        tyro.conf.arg(
            help='Switch to a better removable disk after a disk-space alert'
        ),
    ] = True

    moving_average_time: Annotated[
        units.Seconds,
        cli_metadata.TIME_SPEC,
        tyro.conf.arg(help='How long to average the volume display over'),
    ] = 1.0

    noise_floor: Annotated[
        float,
        Mutable,
        tyro.conf.arg(aliases=('-z',), help='The noise floor in decibels'),
    ] = 70.0

    preview_headroom: Annotated[
        float,
        Mutable,
        tyro.conf.arg(
            help='Headroom in decibels to add to silence preview measurements'
        ),
    ] = 6.0

    record_everything: Annotated[
        bool,
        Mutable,
        tyro.conf.arg(
            aliases=('-R',), help='Start immediately, record everything until end'
        ),
    ] = False

    shortest_file_time: Annotated[
        units.Seconds,
        Mutable,
        cli_metadata.TIME_SPEC,
        tyro.conf.arg(help='Files shorter than this duration get deleted'),
    ] = 1.0

    quiet_after_end: Annotated[
        units.Seconds,
        Mutable,
        cli_metadata.TIME_SPEC,
        tyro.conf.arg(aliases=('-c',), help='How much quiet after the end'),
    ] = 2.0

    quiet_before_start: Annotated[
        units.Seconds,
        Mutable,
        cli_metadata.TIME_SPEC,
        tyro.conf.arg(aliases=('-b',), help='How much quiet before a recording'),
    ] = 1.0

    stop_after_quiet: Annotated[
        units.Seconds,
        Mutable,
        cli_metadata.TIME_SPEC,
        tyro.conf.arg(help='How much quiet before stopping a recording'),
    ] = 20.0

    total_run_time: Annotated[
        units.Seconds,
        Mutable,
        cli_metadata.TIME_SPEC,
        tyro.conf.arg(
            aliases=('-t',), help='How many seconds to record? 0 means forever'
        ),
    ] = 0.0

    @field_validator(
        'audio_buffer_seconds',
        'card_replace_poll_seconds',
        'card_replace_timeout_seconds',
        'disk_poll_seconds',
        'memory_check_period',
    )
    @classmethod
    def validate_positive(cls, value: float) -> float:
        if value <= 0:
            raise ValueError('must be positive')
        return value

    @field_validator('memory_reserve_megabytes', 'minimum_free_space')
    @classmethod
    def validate_minimum_free_space(cls, value: int) -> int:
        if value < 0:
            raise ValueError('must be non-negative')
        return value

    @field_validator(
        'disk_alert_thresholds',
        'disk_removable_emergency',
        'disk_system_emergency',
        'disk_removable_pause',
        'disk_system_pause',
    )
    @classmethod
    def validate_disk_thresholds(cls, values: list[str]) -> list[str]:
        if not values:
            raise ValueError('must not be empty')
        return [disk_threshold.normalize(v) for v in values]
