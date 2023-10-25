import dataclasses as dc
import typing as t
from pathlib import Path

from .audio.file_types import DType, Format, Subtype

TIMESTAMP_FORMAT = '%Y%m%d-%H%M%S'


@dc.dataclass
class Recs:
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
    retain: bool = False
    timestamp_format: str = TIMESTAMP_FORMAT
    use_locking: bool = True
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
    subtype: Subtype | None = None
    dtype: DType | None = None
    #
    # Console and UI settings
    #
    quiet: bool = False
    ui_refresh_rate: float = 23
    sleep_time: float = 0.013
    #
    # Settings relating to times
    #
    silence_before_start: float = 1
    silence_after_end: float = 2
    stop_after_silence: float = 20
    noise_floor: float = 70
    total_run_time: float = 0


RECS = Recs()
