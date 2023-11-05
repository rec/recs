import dataclasses as dc
import json
import typing as t
import warnings
from enum import auto
from functools import cached_property, wraps

import sounddevice as sd
import soundfile as sf
from strenum import StrEnum

from recs.base import RecsError, metadata, times
from recs.base.aliases import Aliases
from recs.base.cfg_raw import CfgRaw
from recs.base.prefix_dict import PrefixDict
from recs.base.to_time import to_time
from recs.base.type_conversions import SDTYPE_TO_SUBTYPE, SUBTYPE_TO_SDTYPE
from recs.base.types import SDTYPE, Format


class Subdirectory(StrEnum):
    channel = auto()
    device = auto()
    time = auto()


Subdirectories = t.Sequence[Subdirectory]
SUBDIRECTORY = PrefixDict({s: s for s in Subdirectory})


class Cfg:
    @wraps(CfgRaw.__init__)
    def __init__(self, *a, **ka) -> None:
        self.cfg = cfg = CfgRaw(*a, **ka)

        if cfg.subtype and not sf.check_format(cfg.format, cfg.subtype):
            raise RecsError(f'{cfg.format} and {cfg.subtype} are incompatible')

        if cfg.subtype is not None and cfg.sdtype is None:
            self.sdtype = SUBTYPE_TO_SDTYPE.get(cfg.subtype, SDTYPE)

        elif cfg.subtype is None and cfg.sdtype is not None:
            subtype = SDTYPE_TO_SUBTYPE.get(cfg.sdtype, None)
            if sf.check_format(cfg.format, subtype):
                self.subtype = subtype
            else:
                msg = f'format={cfg.format:s}, sdtype={cfg.sdtype:s}'
                warnings.warn(f"Can't get subtype for {msg}")
                self.subtype = None
        else:
            self.subtype = cfg.subtype

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
