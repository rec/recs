import dataclasses as dc
import typing as t
from pathlib import Path

import soundfile as sf

from .audio.file_types import DTYPE, DType, Format, Subtype
from .audio.file_types_conversion import DTYPE_TO_SUBTYPE, SUBTYPE_TO_DTYPE


class RecsError(ValueError):
    pass


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

    def __post_init__(self):
        if self.subtype and not sf.check_format(self.format, self.subtype):
            raise RecsError(f'{self.format} and {self.subtype} are incompatible')

        if self.subtype is not None and self.dtype is None:
            self.dtype = SUBTYPE_TO_DTYPE.get(self.subtype, DTYPE)

        elif self.subtype is None and self.dtype is not None:
            subtype = DTYPE_TO_SUBTYPE.get(self.dtype, None)
            if sf.check_format(RECS.format, subtype):
                self.subtype = subtype


RECS = Recs()
