import json
import logging
import warnings
from functools import cached_property
from pathlib import Path

import soundfile
from pydantic import BaseModel, Field, field_validator, model_validator
from typing_extensions import Self

from recs.base.prefix_dict import PrefixDict
from recs.base.type_conversions import SDTYPE_TO_SUBTYPE, SUBTYPE_TO_SDTYPE
from recs.base.types import SDTYPE, Format, SdType, Subtype
from recs.misc import log

from . import device as device_module
from . import metadata, path_pattern, time_settings
from .aliases import Aliases
from .track import source_track


class DirectoryCfg(BaseModel):
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


class GeneralCfg(BaseModel):
    #
    # General purpose settings
    #
    calibrate: bool = False
    dry_run: bool = False
    verbose: bool = False
    info: bool = False
    list_types: bool = False


class DeviceCfg(BaseModel):
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


class SelectionCfg(BaseModel):
    #
    # Exclude or include devices or channels
    #
    exclude: list[str] = Field(default_factory=list)
    include: list[str] = Field(default_factory=list)


class AudioCfg(BaseModel):
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


class ConsoleCfg(BaseModel):
    #
    # Console and UI settings
    #
    clear_terminal: bool = True
    silent: bool = False
    sleep_time_device: float = 0.1
    ui_refresh_rate: float = 23.0


class RecordingCfg(BaseModel):
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
    'recording',
)

CFG_MODEL_TYPES = {
    'directory': DirectoryCfg,
    'general': GeneralCfg,
    'device': DeviceCfg,
    'selection': SelectionCfg,
    'audio': AudioCfg,
    'console': ConsoleCfg,
    'recording': RecordingCfg,
}


def _flat_fields() -> dict[str, str]:
    result: dict[str, str] = {}
    for part, model_type in CFG_MODEL_TYPES.items():
        result.update(dict.fromkeys(model_type.model_fields, part))
    return result


FLAT_FIELDS = _flat_fields()


class Cfg(BaseModel):
    directory: DirectoryCfg = Field(default_factory=DirectoryCfg)
    general: GeneralCfg = Field(default_factory=GeneralCfg)
    device: DeviceCfg = Field(default_factory=DeviceCfg)
    selection: SelectionCfg = Field(default_factory=SelectionCfg)
    audio: AudioCfg = Field(default_factory=AudioCfg)
    console: ConsoleCfg = Field(default_factory=ConsoleCfg)
    recording: RecordingCfg = Field(default_factory=RecordingCfg)

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
        log.VERBOSE = self.verbose
        if self.verbose:
            logging.basicConfig(level=logging.DEBUG)

    @cached_property
    def input_devices(self) -> device_module.InputDevices:
        if self.files:
            return PrefixDict()

        if self.devices.name:
            devices = json.loads(self.devices.read_text())
            return device_module.get_input_devices(devices)

        return device_module.input_devices()

    @cached_property
    def aliases(self) -> Aliases:
        return Aliases(self.alias, self.input_devices)

    @cached_property
    def output_path_pattern(self) -> path_pattern.PathPattern:
        excluded = self.aliases.to_tracks(self.exclude)
        included = self.aliases.to_tracks(self.include)
        selected_devices = sum(
            any(source_track(input_device, excluded, included))
            for input_device in self.input_devices.values()
        )
        short_file_names = self.short_file_names and selected_devices == 1
        return path_pattern.PathPattern(self.output_directory, short_file_names)

    @cached_property
    def metadata_dict(self) -> dict[str, str]:
        return metadata.to_dict(self.metadata)

    @cached_property
    def times(self) -> time_settings.TimeSettings[float]:
        fields = time_settings.TimeSettings.model_fields
        d = {k: getattr(self, k) for k in fields}
        return time_settings.TimeSettings(**d)

    @property
    def files(self) -> list[Path]:
        return self.directory.files

    @property
    def output_directory(self) -> str:
        return self.directory.output_directory

    @property
    def short_file_names(self) -> bool:
        return self.directory.short_file_names

    @property
    def calibrate(self) -> bool:
        return self.general.calibrate

    @property
    def dry_run(self) -> bool:
        return self.general.dry_run

    @property
    def verbose(self) -> bool:
        return self.general.verbose

    @property
    def info(self) -> bool:
        return self.general.info

    @property
    def list_types(self) -> bool:
        return self.general.list_types

    @property
    def alias(self) -> list[str]:
        return self.device.alias

    @property
    def devices(self) -> Path:
        return self.device.devices

    @property
    def exclude(self) -> list[str]:
        return self.selection.exclude

    @property
    def include(self) -> list[str]:
        return self.selection.include

    @property
    def formats(self) -> list[Format]:
        return self.audio.formats

    @property
    def metadata(self) -> list[str]:
        return self.audio.metadata

    @property
    def sdtype(self) -> SdType | None:
        return self.audio.sdtype

    @property
    def subtype(self) -> Subtype | None:
        return self.audio.subtype

    @property
    def clear_terminal(self) -> bool:
        return self.console.clear_terminal

    @property
    def silent(self) -> bool:
        return self.console.silent

    @property
    def sleep_time_device(self) -> float:
        return self.console.sleep_time_device

    @property
    def ui_refresh_rate(self) -> float:
        return self.console.ui_refresh_rate

    @property
    def band_mode(self) -> bool:
        return self.recording.band_mode

    @property
    def infinite_length(self) -> bool:
        return self.recording.infinite_length

    @property
    def longest_file_time(self) -> float:
        return self.recording.longest_file_time

    @property
    def moving_average_time(self) -> float:
        return self.recording.moving_average_time

    @property
    def noise_floor(self) -> float:
        return self.recording.noise_floor

    @property
    def record_everything(self) -> bool:
        return self.recording.record_everything

    @property
    def shortest_file_time(self) -> float:
        return self.recording.shortest_file_time

    @property
    def quiet_after_end(self) -> float:
        return self.recording.quiet_after_end

    @property
    def quiet_before_start(self) -> float:
        return self.recording.quiet_before_start

    @property
    def stop_after_quiet(self) -> float:
        return self.recording.stop_after_quiet

    @property
    def total_run_time(self) -> float:
        return self.recording.total_run_time
