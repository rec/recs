import dataclasses as dc
import json
import typing as t
import warnings
from enum import auto
from functools import cached_property, wraps
from pathlib import Path

import sounddevice as sd
import soundfile as sf
from strenum import StrEnum

from recs.misc import RecsError
from recs.misc.aliases import Aliases
from recs.misc.prefix_dict import PrefixDict

from recs.audio import metadata
from recs.audio.file_types import SDTYPE, Format, SdType, Subtype
from recs.audio.file_types_conversion import SDTYPE_TO_SUBTYPE, SUBTYPE_TO_SDTYPE
from recs.misc import times
from recs.misc.to_time import to_time


class Subdirectory(StrEnum):
    channel = auto()
    device = auto()
    time = auto()


Subdirectories = t.Sequence[Subdirectory]
SUBDIRECTORY = PrefixDict({s: s for s in Subdirectory})


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


class Cfg:
    @wraps(CfgRaw.__init__)
    def __init__(self, *a, **ka) -> None:
        self.cfg = CfgRaw(*a, **ka)

        if self.subtype and not sf.check_format(self.format, self.subtype):
            raise RecsError(f'{self.format} and {self.subtype} are incompatible')

        if self.subtype is not None and self.sdtype is None:
            self.sdtype = SUBTYPE_TO_SDTYPE.get(self.subtype, SDTYPE)

        elif self.subtype is None and self.sdtype is not None:
            subtype = SDTYPE_TO_SUBTYPE.get(self.sdtype, None)
            if sf.check_format(self.format, subtype):
                self.subtype = subtype
            else:
                msg = f'{self.format=:s}, {self.sdtype=:s}'
                warnings.warn(f"Can't get subtype for {msg}")

        self.alias
        self.subdirectory

    def __getattr__(self, k: str) -> t.Any:
        return getattr(self.cfg, k)

    @cached_property
    def alias(self) -> Aliases:
        return Aliases(self.cfg.alias)

    @cached_property
    def metadata(self) -> dict[str, str]:
        return metadata.to_dict(self.cfg.metadata)

    @cached_property
    def subdirectory(self) -> Subdirectories:
        subs = [(s, SUBDIRECTORY.get_value(s)) for s in self.cfg.subdirectory]
        res = tuple(t for s, t in subs if t is not None)

        if bad_subdirectories := [s for s, t in subs if t is None]:
            raise RecsError(f'Bad arguments to --subdirectory: {bad_subdirectories}')

        if len(set(res)) < len(res):
            raise RecsError('Duplicates in --subdirectory')

        return res

    @cached_property
    def times(self) -> times.Times:
        fields = (f.name for f in dc.fields(times.Times))
        d = {k: getattr(self, k) for k in fields}
        try:
            d['longest_file_time'] = to_time(t := d['longest_file_time'])
        except (ValueError, TypeError):
            raise RecsError(f'Do not understand --longest-file-time={t}')

        return times.Times(**d)

    # subdirectories = subdirectory
    # aliases = alias
    # metadata_dict = metadata

    def run(self) -> None:
        from recs.ui.recorder import Recorder

        if self.info:
            info = sd.query_devices(kind=None)
            print(json.dumps(info, indent=4))

        elif self.list_subtypes:
            avail = sf.available_formats()
            fmts = [f.upper() for f in Format]
            formats = {f: [avail[f], sf.available_subtypes(f)] for f in fmts}
            print(json.dumps(formats, indent=4))

        else:
            Recorder(self).run()
