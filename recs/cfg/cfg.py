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

from . import device, metadata, path_pattern, time_settings
from .aliases import Aliases
from .track import source_track


class Cfg(BaseModel):
    # See ./cli.py for full help
    #
    # Directory settings
    #
    files: list[Path] = Field(default_factory=list)
    output_directory: str = ''
    short_file_names: bool = True
    #
    # General purpose settings
    #
    calibrate: bool = False
    dry_run: bool = False
    verbose: bool = False
    info: bool = False
    list_types: bool = False
    #
    # Aliases for input devices or channels
    #
    alias: list[str] = Field(default_factory=list)
    devices: Path = Path()
    #
    # Exclude or include devices or channels
    #
    exclude: list[str] = Field(default_factory=list)
    include: list[str] = Field(default_factory=list)
    #
    # Audio file format and subtype
    #
    formats: list[Format] = Field(default_factory=list)
    metadata: list[str] = Field(default_factory=list)
    sdtype: SdType | None = None
    subtype: Subtype | None = None
    #
    # Console and UI settings
    #
    clear_terminal: bool = True
    silent: bool = False
    sleep_time_device: float = 0.1
    ui_refresh_rate: float = 23.0
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

    def model_post_init(self, context: object) -> None:
        # This constructor has this *global side-effect*, see log.py
        log.VERBOSE = self.verbose
        if self.verbose:
            logging.basicConfig(level=logging.DEBUG)

    @cached_property
    def input_devices(self) -> device.InputDevices:
        if self.files:
            return PrefixDict()

        if self.devices.name:
            devices = json.loads(self.devices.read_text())
            return device.get_input_devices(devices)

        return device.input_devices()

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

    @field_validator('files')
    @classmethod
    def validate_files_exist(cls, files: list[Path]) -> list[Path]:
        if missing := [path for path in files if not path.exists()]:
            suffix = 's' * (len(missing) != 1)
            names = ', '.join(str(path) for path in missing)
            raise ValueError(f'Non-existent file{suffix}: {names}')
        return files

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
