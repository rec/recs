import json
import os
import re
import warnings
from functools import cached_property
from importlib.util import find_spec
from pathlib import Path
from typing import Annotated

import soundfile
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from reccy import logging
from typing_extensions import Self

from recs.base.prefix_dict import PrefixDict
from recs.base.type_conversions import SDTYPE_TO_SUBTYPE, SUBTYPE_TO_SDTYPE
from recs.base.types import SDTYPE, Format, Mutable, RecordKeys, SdType, Subtype

from . import metadata, path_pattern, time_settings
from .aliases import Aliases
from .device import InputDevices, get_input_devices, input_devices
from .track import source_track


class Directory(BaseModel):
    # See ./cli.py for full help
    #
    # Directory settings
    #
    files: list[Path] = Field(default_factory=list)
    output_directory: Annotated[str, Mutable] = ''
    short_file_names: Annotated[bool, Mutable] = True

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
    calibrate: bool = False
    default_record_directory: str = 'recs'
    dry_run: bool = False
    verbose: bool = False
    info: bool = False
    list_types: bool = False
    silence_preview: bool = False
    save_settings: bool | None = None


class Device(BaseModel):
    #
    # Aliases for input devices or channels
    #
    alias: list[str] = Field(default_factory=list)
    devices: Path = Path()
    profiles: Annotated[Path, Mutable] = Path()

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
    exclude: list[str] = Field(default_factory=list)
    include: list[str] = Field(default_factory=list)


class Audio(BaseModel):
    #
    # Audio file format and subtype
    #
    formats: list[Format] = Field(default_factory=list)
    metadata: Annotated[list[str], Mutable] = Field(default_factory=list)
    sdtype: SdType | None = None
    subtype: Subtype | None = None

    @model_validator(mode='after')
    def configure_audio_types(self) -> Self:
        fields_set = set(self.model_fields_set)
        self.formats = self.formats or [Format._default]

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


class Console(BaseModel):
    #
    # Console and UI settings
    #
    clear_terminal: bool = True
    gui: bool = False
    open_output_folder: bool = False
    remote: bool = False
    silent: bool = False
    sleep_time_device: float = 0.1
    ui_refresh_rate: float = 23.0

    @field_validator('sleep_time_device', 'ui_refresh_rate')
    @classmethod
    def validate_positive(cls, value: float) -> float:
        if value <= 0:
            raise ValueError('must be positive')
        return value


class Key(BaseModel):
    #
    # Keyboard event recording
    #
    key_label: Annotated[list[str], Mutable] = Field(default_factory=list)
    record_keys: RecordKeys | None = None
    record_key_all_apps: bool | None = None

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
    audio_buffer_seconds: float = 10.0
    band_mode: Annotated[bool, Mutable] = False
    buffer_status_period: Annotated[float, Mutable] = 1.0
    buffer_warning_fraction: Annotated[float, Mutable] = 0.75
    channel_noise_floors: Annotated[
        dict[str, dict[str, float | None]], Mutable
    ] = Field(default_factory=dict)
    infinite_length: bool = False
    longest_file_time: Annotated[float, Mutable] = 0.0
    minimum_free_space: Annotated[int, Mutable] = 0
    disk_alert_thresholds: Annotated[list[str], Mutable] = Field(
        default_factory=lambda: ['30m', '10m', '2m']
    )
    disk_removable_emergency: Annotated[list[str], Mutable] = Field(
        default_factory=lambda: ['200MB', '30s']
    )
    disk_system_emergency: Annotated[list[str], Mutable] = Field(
        default_factory=lambda: ['2GB', '2m']
    )
    disk_removable_pause: Annotated[list[str], Mutable] = Field(
        default_factory=lambda: ['200MB', '30s']
    )
    disk_system_pause: Annotated[list[str], Mutable] = Field(
        default_factory=lambda: ['2GB', '2m']
    )
    disk_poll_seconds: Annotated[float, Mutable] = 1.0
    disk_auto_switch: Annotated[bool, Mutable] = True
    moving_average_time: float = 1.0
    noise_floor: Annotated[float, Mutable] = 70.0
    preview_headroom: Annotated[float, Mutable] = 6.0
    record_everything: Annotated[bool, Mutable] = False
    shortest_file_time: Annotated[float, Mutable] = 1.0
    quiet_after_end: Annotated[float, Mutable] = 2.0
    quiet_before_start: Annotated[float, Mutable] = 1.0
    stop_after_quiet: Annotated[float, Mutable] = 20.0
    total_run_time: Annotated[float, Mutable] = 0.0

    @field_validator(
        'audio_buffer_seconds', 'buffer_status_period', 'disk_poll_seconds'
    )
    @classmethod
    def validate_positive(cls, value: float) -> float:
        if value <= 0:
            raise ValueError('must be positive')
        return value

    @field_validator('buffer_warning_fraction')
    @classmethod
    def validate_buffer_warning_fraction(cls, value: float) -> float:
        if not 0 < value <= 1:
            raise ValueError('must be between 0 and 1')
        return value

    @field_validator('minimum_free_space')
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
        for value in values:
            if not re.fullmatch(r'\d+(?:\.\d+)?(?:KB|MB|GB|s|m|h)?', value):
                raise ValueError(f'invalid disk threshold: {value}')
        return values


CFG_PARTS = (
    'directory',
    'general',
    'device',
    'selection',
    'audio',
    'console',
    'keys',
    'recording',
)

CFG_MODEL_TYPES = {
    'directory': Directory,
    'general': General,
    'device': Device,
    'selection': Selection,
    'audio': Audio,
    'console': Console,
    'keys': Key,
    'recording': Recording,
}


def _flat_fields() -> dict[str, str]:
    result: dict[str, str] = {}
    for part, model_type in CFG_MODEL_TYPES.items():
        result.update(dict.fromkeys(model_type.model_fields, part))
    return result


FLAT_FIELDS = _flat_fields()


class Cfg(BaseModel):
    model_config = ConfigDict(extra='forbid')

    directory: Directory = Field(default_factory=Directory)
    general: General = Field(default_factory=General)
    device: Device = Field(default_factory=Device)
    selection: Selection = Field(default_factory=Selection)
    audio: Audio = Field(default_factory=Audio)
    console: Console = Field(default_factory=Console)
    keys: Key = Field(default_factory=Key)
    recording: Recording = Field(default_factory=Recording)

    def __init__(self, **data: object) -> None:
        if unknown := set(data) - set(CFG_PARTS) - set(FLAT_FIELDS):
            super().__init__(**{k: data[k] for k in unknown})
            return

        fields_set = set(data) - set(CFG_PARTS)
        grouped: dict[str, dict[str, object]] = {part: {} for part in CFG_PARTS}
        nested = {part: data.pop(part) for part in CFG_PARTS if part in data}

        for field, value in data.items():
            grouped[FLAT_FIELDS[field]][field] = value

        model_data: dict[str, object] = {}
        for part, values in grouped.items():
            if values:
                model_data[part] = values
            elif part in nested:
                model_data[part] = nested[part]
        super().__init__(**model_data)
        object.__setattr__(self, '__pydantic_fields_set__', fields_set)

    @classmethod
    def raw_defaults(cls) -> Self:
        return cls.model_construct(
            **{
                part: model_type.model_construct()
                for part, model_type in CFG_MODEL_TYPES.items()
            },
            _fields_set=set(),
        )

    def model_post_init(self, context: object) -> None:
        if self.general.verbose:
            logging.configure(verbose=True)
        self._configure_keys()

    @property
    def save_settings(self) -> bool:
        if self.general.save_settings is not None:
            return self.general.save_settings
        return os.environ.get('RECS_DAEMON') == '1'

    @cached_property
    def mutable_attributes(self) -> frozenset[str]:
        return frozenset(_mutable_attributes(type(self)))

    def get_attr(self, address: str) -> object:
        part, field = _cfg_address(address)
        value = getattr(self, part).model_dump(mode='json')
        return value[field]

    def set_attr(self, address: str, value: object) -> Self:
        part, field = _cfg_address(address)
        if address not in self.mutable_attributes:
            raise ValueError(f'Immutable configuration attribute: {address}')
        data = self.model_dump(mode='json')
        section = data[part]
        assert isinstance(section, dict)
        section[field] = value
        return type(self)(**data)

    def _configure_keys(self) -> None:
        fields_set = set(self.model_fields_set)
        record_keys = self.keys.record_keys
        record_key_all_apps = self.keys.record_key_all_apps

        if self.console.gui:
            record_keys = record_keys or RecordKeys.all
            if record_key_all_apps is None:
                record_key_all_apps = True
        elif _pynput_available():
            record_keys = record_keys or RecordKeys.all
            if record_key_all_apps is None:
                record_key_all_apps = record_keys != RecordKeys.all
        else:
            record_keys = record_keys or RecordKeys.press
            if record_keys == RecordKeys.all:
                raise ValueError('record_keys cannot be all without pynput')
            if record_key_all_apps:
                raise ValueError('record_key_all_apps must be False without pynput')
            record_key_all_apps = False

        keys = self.keys.model_copy(
            update={
                'record_keys': record_keys,
                'record_key_all_apps': record_key_all_apps,
            }
        )
        object.__setattr__(self, 'keys', keys)
        object.__setattr__(self, '__pydantic_fields_set__', fields_set)

    @cached_property
    def input_devices(self) -> InputDevices:
        if self.directory.files:
            return PrefixDict()

        if self.device.devices.name:
            devices = json.loads(self.device.devices.read_text())
            return get_input_devices(devices)

        return input_devices()

    @cached_property
    def aliases(self) -> Aliases:
        return Aliases(self.device.alias, self.input_devices)

    @cached_property
    def output_path_pattern(self) -> path_pattern.PathPattern:
        excluded = self.aliases.to_tracks(self.selection.exclude)
        included = self.aliases.to_tracks(self.selection.include)
        selected_devices = sum(
            any(source_track(input_device, excluded, included))
            for input_device in self.input_devices.values()
        )
        short_file_names = self.directory.short_file_names and selected_devices == 1
        return path_pattern.PathPattern(
            self.directory.output_directory, short_file_names
        )

    @cached_property
    def device_profiles(self) -> dict[str, dict[str, object]]:
        path = self.device.profiles
        if not path.name:
            return {}
        if not path.exists():
            raise ValueError(f'{path} does not exist')
        data = json.loads(path.read_text())
        if not data:
            raise ValueError(f'{path} contains no profiles')
        if not isinstance(data, dict):
            raise ValueError(f'{path} must contain a JSON object')

        profiles: dict[str, dict[str, object]] = {}
        for name, values in data.items():
            if not isinstance(name, str) or not isinstance(values, dict):
                raise ValueError(f'{path} must map device names to objects')
            profiles[name] = values
        return profiles

    def with_device_profile(self, source_name: str) -> Self:
        values = self.device_profiles.get(source_name)
        if not values:
            return self

        data = self.model_dump()
        for field, value in values.items():
            if field in CFG_PARTS:
                if not isinstance(value, dict):
                    raise ValueError(f'Profile section {field} must be an object')
                data[field] = data[field] | value
            elif field in FLAT_FIELDS:
                data[FLAT_FIELDS[field]][field] = value
            else:
                raise ValueError(f'Unknown profile field: {field}')
        return type(self)(**data)

    @cached_property
    def metadata_dict(self) -> dict[str, str]:
        return metadata.to_dict(self.audio.metadata)

    @cached_property
    def times(self) -> time_settings.TimeSettings[float]:
        fields = time_settings.TimeSettings.model_fields
        d = {k: getattr(self.recording, k) for k in fields}
        return time_settings.TimeSettings(**d)


def _mutable_attributes(model_type: type[BaseModel], prefix: str = '') -> list[str]:
    result: list[str] = []
    for name, field in model_type.model_fields.items():
        address = f'{prefix}.{name}' if prefix else name
        annotation = field.annotation
        if isinstance(annotation, type) and issubclass(annotation, BaseModel):
            result.extend(_mutable_attributes(annotation, address))
        elif Mutable in field.metadata:
            result.append(address)
    return result


def _cfg_address(address: str) -> tuple[str, str]:
    part, separator, field = address.partition('.')
    if not separator or not part or not field or '.' in field:
        raise ValueError(f'Invalid configuration address: {address}')
    if part not in CFG_MODEL_TYPES or field not in CFG_MODEL_TYPES[part].model_fields:
        raise ValueError(f'Unknown configuration address: {address}')
    return part, field


def _pynput_available() -> bool:
    return find_spec('pynput') is not None
