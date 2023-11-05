import dataclasses as dc
import typing as t
from pathlib import Path

from recs.audio.file_types import Format, SdType, Subtype


@dc.dataclass
class CfgRaw:
    # See ./cli.py for full help
    #
    # Directory settings
    #
    path: Path = Path()
    subdirectory: t.Sequence[str] = ()
    #
    # General purpose settings
    #
    dry_run: bool = False
    info: bool = False
    list_subtypes: bool = False
    verbose: bool = False
    #
    # Aliases for input devices or channels
    #
    alias: t.Sequence[str] = ()
    #
    # Exclude or include devices or channels
    #
    exclude: t.Sequence[str] = ()
    include: t.Sequence[str] = ()
    #
    # Audio file format and subtype
    #
    format: Format = Format.flac
    metadata: t.Sequence[str] = ()
    sdtype: SdType | None = None
    subtype: Subtype | None = None
    #
    # Console and UI settings
    #
    quiet: bool = False
    retain: bool = True
    ui_refresh_rate: float = 23
    sleep_time: float = 0.013
    #
    # Settings relating to times
    #
    infinite_length: bool = False
    longest_file_time: str = '0'  # In HH:MM:SS.SSSS
    moving_average_time: float = 1
    noise_floor: float = 70
    silence_after_end: float = 2
    silence_before_start: float = 1
    stop_after_silence: float = 20
    total_run_time: float = 0
