import json
import logging
import warnings
from functools import cached_property

import soundfile
from pydantic import model_validator
from typing_extensions import Self

from recs.base.cfg_raw import CfgRaw
from recs.base.prefix_dict import PrefixDict
from recs.base.type_conversions import SDTYPE_TO_SUBTYPE, SUBTYPE_TO_SDTYPE
from recs.base.types import SDTYPE, Format
from recs.misc import log

from . import device, metadata, path_pattern, time_settings
from .aliases import Aliases
from .track import source_track


class Cfg(CfgRaw):
    def model_post_init(self, context: object) -> None:
        # This constructor has this *global side-effect*, see log.py
        log.VERBOSE = self.verbose
        if self.verbose:
            logging.basicConfig(level=logging.DEBUG)

    @cached_property
    def input_devices(self) -> device.InputDevices:
        if self.files:
            return PrefixDict()

        if self.devices.name:
            devices = json.loads(self.devices.read_text())
            return device.get_input_devices(devices)

        return device.input_devices()

    @cached_property
    def aliases(self) -> Aliases:
        return Aliases(self.alias, self.input_devices)

    @cached_property
    def output_path_pattern(self) -> path_pattern.PathPattern:
        excluded = self.aliases.to_tracks(self.exclude)
        included = self.aliases.to_tracks(self.include)
        selected_devices = sum(
            any(source_track(input_device, excluded, included))
            for input_device in self.input_devices.values()
        )
        short_file_names = self.short_file_names and selected_devices == 1
        return path_pattern.PathPattern(self.output_directory, short_file_names)

    @cached_property
    def metadata_dict(self) -> dict[str, str]:
        return metadata.to_dict(self.metadata)

    @cached_property
    def times(self) -> time_settings.TimeSettings[float]:
        fields = time_settings.TimeSettings.model_fields
        d = {k: getattr(self, k) for k in fields}
        return time_settings.TimeSettings(**d)

    @model_validator(mode='after')
    def configure_audio_types(self) -> Self:
        fields_set = set(self.model_fields_set)
        self.formats = self.formats or [Format._default]

        if self.subtype:
            pass
        elif not self.sdtype or 'sdtype' not in fields_set:
            self.subtype = None
        else:
            subtype = SDTYPE_TO_SUBTYPE[self.sdtype]

            if soundfile.check_format(self.formats[0], subtype):
                self.subtype = subtype
            else:
                self.subtype = None
                msg = f'formats={self.formats[0]:s}, sdtype={self.sdtype:s}'
                warnings.warn(f"Can't get subtype for {msg}", stacklevel=2)

        if self.sdtype and 'sdtype' in fields_set:
            pass
        elif self.subtype:
            self.sdtype = SUBTYPE_TO_SDTYPE.get(self.subtype, SDTYPE)
        else:
            self.sdtype = SDTYPE
        object.__setattr__(self, '__pydantic_fields_set__', fields_set)
        return self
