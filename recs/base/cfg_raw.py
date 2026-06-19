import json
from pathlib import Path

import soundfile
from pydantic import BaseModel, Field, field_validator, model_validator
from typing_extensions import Self

from .types import Format, SdType, Subtype


class CfgRaw(BaseModel):
    # See ./cli.py for full help
    #
    # Directory settings
    #
    files: list[Path] = Field(default_factory=list)
    output_directory: str = ''
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
    clear: bool = False
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
    def validate_format_and_subtype(self) -> Self:
        audio_format = self.formats[0] if self.formats else Format._default
        if self.subtype and not soundfile.check_format(audio_format, self.subtype):
            raise ValueError(f'{audio_format} and {self.subtype} are incompatible')
        return self
