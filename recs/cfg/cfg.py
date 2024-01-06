import dataclasses as dc
import json
import logging
import typing as t
import warnings
from functools import wraps

import soundfile as sf

from recs.base import RecsError
from recs.base.cfg_raw import CfgRaw
from recs.base.type_conversions import SDTYPE_TO_SUBTYPE, SUBTYPE_TO_SDTYPE
from recs.base.types import SDTYPE, Format, SdType, Subtype
from recs.misc import log

from . import device, metadata, path_pattern, time_settings
from .aliases import Aliases


class Cfg:
    devices: device.InputDevices
    format: Format
    subtype: Subtype | None
    sdtype: SdType

    @wraps(CfgRaw.__init__)
    def __init__(self, *a, **ka) -> None:
        self.cfg = cfg = CfgRaw(*a, **ka)

        # This constructor has this *global side-effect*, see log.py
        log.VERBOSE = cfg.verbose
        if cfg.verbose:
            logging.basicConfig(level=logging.DEBUG)

        self.path = path_pattern.PathPattern(cfg.path)

        self.format = t.cast(Format, cfg.format)

        if cfg.subtype:
            self.subtype = t.cast(Subtype, cfg.subtype)
        elif not cfg.sdtype:
            self.subtype = None
        else:
            subtype = SDTYPE_TO_SUBTYPE[t.cast(SdType, cfg.sdtype)]

            if sf.check_format(self.format, subtype):
                self.subtype = subtype
            else:
                self.subtype = None
                msg = f'format={self.format:s}, sdtype={cfg.sdtype:s}'
                warnings.warn(f"Can't get subtype for {msg}")

        if self.subtype and not sf.check_format(self.format, self.subtype):
            raise RecsError(f'{self.format} and {self.subtype} are incompatible')

        if cfg.sdtype:
            self.sdtype = t.cast(SdType, cfg.sdtype)
        elif self.subtype:
            self.sdtype = SUBTYPE_TO_SDTYPE.get(self.subtype, SDTYPE)
        else:
            self.sdtype = SDTYPE

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
        return time_settings.TimeSettings(**d)
