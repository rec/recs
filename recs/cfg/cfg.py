import json
import logging
import warnings
from functools import cached_property
from importlib.util import find_spec
from pathlib import Path

import soundfile
from pydantic import BaseModel, Field, field_validator, model_validator
from typing_extensions import Self

from recs.base.prefix_dict import PrefixDict
from recs.base.type_conversions import SDTYPE_TO_SUBTYPE, SUBTYPE_TO_SDTYPE
from recs.base.types import SDTYPE, Format, RecordKeys, SdType, Subtype
from recs.misc import log

from . import device as device_module
from . import metadata, path_pattern, time_settings
from .aliases import Aliases
from .track import source_track


class Directory(BaseModel):
    # See ./cli.py for full help
    #
    # Directory settings
    #
    files: list[Path] = Field(default_factory=list)
    output_directory: str = ''
    short_file_names: bool = True

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
    dry_run: bool = False
    verbose: bool = False
    info: bool = False
    list_types: bool = False


class Device(BaseModel):
    #
    # Aliases for input devices or channels
    #
    alias: list[str] = Field(default_factory=list)
    devices: Path = Path()

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
    metadata: list[str] = Field(default_factory=list)
    sdtype: SdType | None = None
    subtype: Subtype | None = None

    @model_validator(mode='after')
    def configure_audio_types(self) -> Self:
        fields_set = set(self.model_fields_set)
        self.formats = self.formats or [Format._default]

        if self.subtype and not soundfile.check_format(
            self.formats[0], self.subtype
        ):
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
    silent: bool = False
    sleep_time_device: float = 0.1
    ui_refresh_rate: float = 23.0


class Key(BaseModel):
    #
    # Keyboard event recording
    #
    record_keys: RecordKeys | None = None
    record_key_all_apps: bool | None = None


class Recording(BaseModel):
    #
    # Settings relating to times
    #
    band_mode: bool = True
    infinite_length: bool = False
    longest_file_time: float = 0.0
    moving_average_time: float = 1.0
    noise_floor: float = 70.0
    record_everything: bool = False
    shortest_file_time: float = 1.0
    quiet_after_end: float = 2.0
    quiet_before_start: float = 1.0
    stop_after_quiet: float = 20.0
    total_run_time: float = 0.0


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
    directory: Directory = Field(default_factory=Directory)
    general: General = Field(default_factory=General)
    device: Device = Field(default_factory=Device)
    selection: Selection = Field(default_factory=Selection)
    audio: Audio = Field(default_factory=Audio)
    console: Console = Field(default_factory=Console)
    keys: Key = Field(default_factory=Key)
    recording: Recording = Field(default_factory=Recording)

    def __init__(self, **data: object) -> None:
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
        # This constructor has this *global side-effect*, see log.py
        log.VERBOSE = self.general.verbose
        if self.general.verbose:
            logging.basicConfig(level=logging.DEBUG)
        self._configure_keys()

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
    def input_devices(self) -> device_module.InputDevices:
        if self.directory.files:
            return PrefixDict()

        if self.device.devices.name:
            devices = json.loads(self.device.devices.read_text())
            return device_module.get_input_devices(devices)

        return device_module.input_devices()

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
        short_file_names = (
            self.directory.short_file_names and selected_devices == 1
        )
        return path_pattern.PathPattern(
            self.directory.output_directory, short_file_names
        )

    @cached_property
    def metadata_dict(self) -> dict[str, str]:
        return metadata.to_dict(self.audio.metadata)

    @cached_property
    def times(self) -> time_settings.TimeSettings[float]:
        fields = time_settings.TimeSettings.model_fields
        d = {k: getattr(self.recording, k) for k in fields}
        return time_settings.TimeSettings(**d)


def _pynput_available() -> bool:
    return find_spec('pynput') is not None
