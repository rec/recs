import json
import logging
import typing as t
import warnings
from functools import wraps

import soundfile

from recs.base.cfg_raw import CfgRaw
from recs.base.prefix_dict import PrefixDict
from recs.base.type_conversions import SDTYPE_TO_SUBTYPE, SUBTYPE_TO_SDTYPE
from recs.base.types import SDTYPE, Format, SdType, Subtype
from recs.misc import log

from . import device, metadata, path_pattern, time_settings
from .aliases import Aliases


class Cfg:
    devices: device.InputDevices
    formats: t.Sequence[Format]
    subtype: Subtype | None
    sdtype: SdType

    @wraps(CfgRaw.__init__)
    def __init__(self, *a: t.Any, **ka: t.Any) -> None:
        self.cfg = cfg = CfgRaw(*a, **ka)

        # This constructor has this *global side-effect*, see log.py
        log.VERBOSE = cfg.verbose
        if cfg.verbose:
            logging.basicConfig(level=logging.DEBUG)

        self.output_directory = path_pattern.PathPattern(cfg.output_directory)

        self.files = list(cfg.files)

        self.formats = list(cfg.formats) or [Format._default]

        if cfg.subtype:
            self.subtype = cfg.subtype
        elif not cfg.sdtype:
            self.subtype = None
        else:
            subtype = SDTYPE_TO_SUBTYPE[cfg.sdtype]

            if soundfile.check_format(self.formats[0], subtype):
                self.subtype = subtype
            else:
                self.subtype = None
                msg = f'formats={self.formats[0]:s}, sdtype={cfg.sdtype:s}'
                warnings.warn(f"Can't get subtype for {msg}", stacklevel=2)

        if cfg.sdtype:
            self.sdtype = cfg.sdtype
        elif self.subtype:
            self.sdtype = SUBTYPE_TO_SDTYPE.get(self.subtype, SDTYPE)
        else:
            self.sdtype = SDTYPE

        if self.files:
            self.devices = PrefixDict()

        elif cfg.devices.name:
            devices = json.loads(cfg.devices.read_text())
            self.devices = device.get_input_devices(devices)

        else:
            self.devices = device.input_devices()

        self.aliases = Aliases(cfg.alias, self.devices)
        self.metadata = metadata.to_dict(cfg.metadata)
        self.times = self._times()

    def __getattr__(self, k: str) -> t.Any:
        return getattr(self.cfg, k)

    def _times(self) -> time_settings.TimeSettings[float]:
        fields = time_settings.TimeSettings.model_fields
        d = {k: getattr(self, k) for k in fields}
        return time_settings.TimeSettings(**d)
