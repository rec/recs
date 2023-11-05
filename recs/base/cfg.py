import dataclasses as dc
import json
import typing as t
import warnings
from enum import auto
from functools import cached_property, wraps

import sounddevice as sd
import soundfile as sf
from strenum import StrEnum

from . import RecsError, metadata, times
from .aliases import Aliases
from .cfg_raw import CfgRaw
from .prefix_dict import PrefixDict
from .to_time import to_time
from .type_conversions import FORMATS, SDTYPE_TO_SUBTYPE, SUBTYPE_TO_SDTYPE, SUBTYPES
from .types import SDTYPE, Format, SdType, Subtype


class Subdirectory(StrEnum):
    channel = auto()
    device = auto()
    time = auto()


Subdirectories = t.Sequence[Subdirectory]
SUBDIRECTORY = PrefixDict({s: s for s in Subdirectory})


class Cfg:
    format: Format
    sdtype: SdType | None = None
    subtype: Subtype | None = None

    @wraps(CfgRaw.__init__)
    def __init__(self, *a, **ka) -> None:
        self.cfg = cfg = CfgRaw(*a, **ka)
        self.format = FORMATS[cfg.format]
        if cfg.sdtype:
            self.sdtype = SdType[cfg.sdtype]
        if cfg.subtype:
            self.subtype = SUBTYPES[cfg.subtype]

        if self.subtype and not sf.check_format(self.format, self.subtype):
            raise RecsError(f'{self.format} and {self.subtype} are incompatible')

        if self.subtype is not None and self.sdtype is None:
            self.sdtype = SUBTYPE_TO_SDTYPE.get(self.subtype, SDTYPE)

        elif self.subtype is None and self.sdtype is not None:
            subtype = SDTYPE_TO_SUBTYPE.get(self.sdtype, None)
            if sf.check_format(self.format, subtype):
                self.subtype = subtype
            else:
                msg = f'format={self.format:s}, sdtype={self.sdtype:s}'
                warnings.warn(f"Can't get subtype for {msg}")
                self.subtype = None
        else:
            self.subtype = self.subtype

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
