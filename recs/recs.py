import dataclasses as dc
import json
import typing as t
from pathlib import Path

import sounddevice as sd

from .audio.channel_writer import TIMESTAMP_FORMAT
from .audio.file_types import DTYPE, DType, Format, Subtype

VERBOSE = False


@dc.dataclass(frozen=True)
class Recs:
    #
    # General purpose settings
    #
    dry_run: bool = False
    info: bool = False
    path: Path = Path()
    retain: bool = False
    timestamp_format: str = TIMESTAMP_FORMAT
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
    subtype: Subtype = Subtype._none
    dtype: DType = DTYPE
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

    def __call__(self) -> None:
        global VERBOSE

        VERBOSE = self.verbose

        if self.info:
            info = sd.query_devices(kind=None)
            print(json.dumps(info, indent=2))
        else:
            from .ui.session import Session

            Session(self).run()


RECS = Recs()
