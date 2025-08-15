import dataclasses as dc
import typing as t
from pathlib import Path


@dc.dataclass
class CfgRaw:
    # See ./cli.py for full help
    #
    # Directory settings
    #
    files: list[str] = dc.field(default_factory=list)
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
    alias: t.Sequence[str] = ()
    devices: Path = Path()
    #
    # Exclude or include devices or channels
    #
    exclude: t.Sequence[str] = ()
    include: t.Sequence[str] = ()
    #
    # Audio file format and subtype
    #
    formats: t.Sequence[str] = ()
    metadata: t.Sequence[str] = ()
    sdtype: str = ''
    subtype: str = ''
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

    asdict = dc.asdict
