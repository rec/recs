import dataclasses as dc
import json
import typing as t
import warnings
from functools import wraps

import soundfile as sf

from recs.base import RecsError, times
from recs.base.cfg_raw import CfgRaw
from recs.base.type_conversions import (
    FORMATS,
    SDTYPE_TO_SUBTYPE,
    SUBTYPE_TO_SDTYPE,
    SUBTYPES,
)
from recs.base.types import SDTYPE, Format, SdType, Subtype

from . import device, metadata, path_pattern, time_settings
from .aliases import Aliases


class Cfg:
    devices: device.InputDevices
    format: Format
    sdtype: SdType | None = None
    subtype: Subtype | None = None

    @wraps(CfgRaw.__init__)
    def __init__(self, *a, **ka) -> None:
        self.cfg = cfg = CfgRaw(*a, **ka)
        self.path = path_pattern.PathPattern(cfg.path)

        def get(d, key, flag):
            if not key:
                return None
            try:
                return d[key]
            except KeyError:
                raise RecsError(f'Cannot understand --{flag}="{key}"') from None

        self.format = get(FORMATS, cfg.format, 'format')
        self.sdtype = get(SdType, cfg.sdtype, 'sdtype')
        self.subtype = get(SUBTYPES, cfg.subtype, 'subtype')

        if self.subtype:
            if not self.sdtype:
                self.sdtype = SUBTYPE_TO_SDTYPE.get(self.subtype, SDTYPE)

            if not sf.check_format(self.format, self.subtype):
                raise RecsError(f'{self.format} and {self.subtype} are incompatible')

        elif self.sdtype:
            subtype = SDTYPE_TO_SUBTYPE.get(self.sdtype, None)

            if sf.check_format(self.format, subtype):
                self.subtype = subtype
            else:
                msg = f'format={self.format:s}, sdtype={self.sdtype:s}'
                warnings.warn(f"Can't get subtype for {msg}")

        if cfg.devices.name:
            if not cfg.devices.exists():
                raise RecsError(f'{cfg.devices} does not exist')
            devices = json.loads(cfg.devices.read_text())
            assert devices
            self.devices = device.get_input_devices(devices)

        else:
            self.devices = device.input_devices()

        self.aliases = Aliases(cfg.alias, self.devices)
        self.metadata = metadata.to_dict(cfg.metadata)
        self.times = self._times()

    def __getattr__(self, k: str) -> t.Any:
        return getattr(self.cfg, k)

    def _times(self) -> time_settings.TimeSettings:
        fields = (f.name for f in dc.fields(time_settings.TimeSettings))
        d = {k: getattr(self, k) for k in fields}

        try:
            d['longest_file_time'] = times.to_time(t := d['longest_file_time'])
        except (ValueError, TypeError):
            raise RecsError(f'Do not understand --longest-file-time={t}')
        try:
            d['shortest_file_time'] = times.to_time(t := d['shortest_file_time'])
        except (ValueError, TypeError):
            raise RecsError(f'Do not understand --shortest-file-time={t}')

        return time_settings.TimeSettings(**d)
