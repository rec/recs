from pathlib import Path

from pydantic import BaseModel, Field


class CfgRaw(BaseModel):
    # See ./cli.py for full help
    #
    # Directory settings
    #
    files: list[str] = Field(default_factory=list)
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
    formats: list[str] = Field(default_factory=list)
    metadata: list[str] = Field(default_factory=list)
    sdtype: str | None = None
    subtype: str | None = None
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
