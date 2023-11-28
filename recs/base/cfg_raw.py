import dataclasses as dc
import typing as t
from pathlib import Path

from .types import Format


@dc.dataclass
class CfgRaw:
    # See ./cli.py for full help
    #
    # Directory settings
    #
    path: str = ''
    #
    # General purpose settings
    #
    calibrate: bool = False
    dry_run: bool = False
    info: bool = False
    list_types: bool = False
    verbose: bool = False
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
    format: str = Format.flac
    metadata: t.Sequence[str] = ()
    sdtype: str = ''
    subtype: str = ''
    #
    # Console and UI settings
    #
    silent: bool = False
    retain: bool = True
    ui_refresh_rate: float = 23
    sleep_time_device: float = 0.1
    sleep_time_live: float = 0.013
    sleep_time_spin: float = 0.1
    #
    # Settings relating to times
    #
    infinite_length: bool = False
    longest_file_time: str = '0'  # In HH:MM:SS.SSSS
    moving_average_time: float = 1
    noise_floor: float = 70
    shortest_file_time: str = '1'  # In HH:MM:SS.SSSS
    quiet_after_end: float = 2
    quiet_before_start: float = 1
    stop_after_quiet: float = 20
    total_run_time: float = 0

    asdict = dc.asdict
