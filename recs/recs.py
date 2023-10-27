import dataclasses as dc
import typing as t
from enum import StrEnum, auto
from functools import cached_property
from pathlib import Path

import soundfile as sf

from .audio import times
from .audio.file_types import DTYPE, DType, Format, Subtype
from .audio.file_types_conversion import DTYPE_TO_SUBTYPE, SUBTYPE_TO_DTYPE
from .audio.prefix_dict import PrefixDict
from .error import RecsError
from .ui.aliases import Aliases


class Subdirectory(StrEnum):
    channel = auto()
    device = auto()
    time = auto()


SUBDIRECTORY = PrefixDict({s: s for s in Subdirectory})


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

    @cached_property
    def aliases(self) -> Aliases:
        return Aliases(self.alias)

    @cached_property
    def subdirectories(self) -> tuple[Subdirectory, ...]:
        subs = [(s, SUBDIRECTORY.get_value(s)) for s in self.subdirectory]
        if bad_subdirectories := [s for s, t in subs if t is None]:
            raise RecsError(f'Bad arguments to --subdirectory {bad_subdirectories}')
        res = tuple(t for s, t in subs if t is not None)
        if len(set(res)) < len(res):
            raise RecsError(f'Duplicates in --subdirectory {res}')
        return res

    @cached_property
    def times(self) -> times.Times:
        fields = (f.name for f in dc.fields(times.Times))
        return times.Times(**{k: getattr(self, k) for k in fields})

    def __post_init__(self):
        if self.subtype and not sf.check_format(self.format, self.subtype):
            raise RecsError(f'{self.format} and {self.subtype} are incompatible')

        if self.subtype is not None and self.dtype is None:
            self.dtype = SUBTYPE_TO_DTYPE.get(self.subtype, DTYPE)

        elif self.subtype is None and self.dtype is not None:
            subtype = DTYPE_TO_SUBTYPE.get(self.dtype, None)
            if sf.check_format(RECS.format, subtype):
                self.subtype = subtype

        self.subdirectories


RECS = Recs()
