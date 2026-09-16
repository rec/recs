import json
import os
from functools import cached_property
from importlib.util import find_spec
from typing import Self, cast

from pydantic import BaseModel, ConfigDict, Field
from reccy.configuration import units
from reccy.runtime import logging

from recs.base.prefix_dict import PrefixDict
from recs.base.types import Mutable, RecordKeys
from recs.cfg.sections import (
    Audio,
    Console,
    Device,
    Directory,
    General,
    Key,
    Midi,
    Osc,
    Recording,
    Selection,
)

from . import metadata, path_pattern, time_settings
from .aliases import Aliases
from .device import InputDevices, get_input_devices, input_devices
from .track import source_track

CFG_PARTS = (
    'directory',
    'general',
    'device',
    'selection',
    'audio',
    'midi',
    'osc',
    'console',
    'keys',
    'recording',
)


CFG_MODEL_TYPES = {
    'directory': Directory,
    'general': General,
    'device': Device,
    'selection': Selection,
    'audio': Audio,
    'midi': Midi,
    'osc': Osc,
    'console': Console,
    'keys': Key,
    'recording': Recording,
}


def _flat_fields() -> dict[str, str]:
    result: dict[str, str] = {}
    for part, model_type in CFG_MODEL_TYPES.items():
        result.update(dict.fromkeys(model_type.model_fields, part))
    return result


FLAT_FIELDS = _flat_fields()


class Cfg(BaseModel):
    model_config = ConfigDict(extra='forbid')

    directory: Directory = Field(default_factory=Directory)
    general: General = Field(default_factory=General)
    device: Device = Field(default_factory=Device)
    selection: Selection = Field(default_factory=Selection)
    audio: Audio = Field(default_factory=Audio)
    midi: Midi = Field(default_factory=Midi)
    osc: Osc = Field(default_factory=Osc)
    console: Console = Field(default_factory=Console)
    keys: Key = Field(default_factory=Key)
    recording: Recording = Field(default_factory=Recording)

    def __init__(self, **data: object) -> None:
        if unknown := set(data) - set(CFG_PARTS) - set(FLAT_FIELDS):
            super().__init__(**{k: data[k] for k in unknown})
            return

        fields_set = set(data) - set(CFG_PARTS)
        grouped: dict[str, dict[str, object]] = {part: {} for part in CFG_PARTS}
        nested = {part: data.pop(part) for part in CFG_PARTS if part in data}

        for field, value in data.items():
            grouped[FLAT_FIELDS[field]][field] = value

        model_data: dict[str, object] = {}
        for part, values in grouped.items():
            if values:
                model_data[part] = values
            elif part in nested:
                model_data[part] = nested[part]
        super().__init__(**model_data)
        object.__setattr__(self, '__pydantic_fields_set__', fields_set)

    @classmethod
    def raw_defaults(cls) -> Self:
        return cls.model_construct(
            **{
                part: model_type.model_construct()
                for part, model_type in CFG_MODEL_TYPES.items()
            },
            _fields_set=set(),
        )

    def model_post_init(self, context: object) -> None:
        if self.general.verbose:
            logging.configure(verbose=True)
        self._configure_keys()

    @property
    def save_settings(self) -> bool:
        if self.general.save_settings is not None:
            return self.general.save_settings
        return os.environ.get('RECS_DAEMON') == '1'

    @cached_property
    def mutable_attributes(self) -> frozenset[str]:
        return frozenset(_mutable_attributes(type(self)))

    def get_attr(self, address: str, *, authored: bool = False) -> object:
        part, field = _cfg_address(address)
        section = getattr(self, part)
        value = (
            units.authored_dump(section, mode='json')
            if authored
            else units.runtime_dump(section, mode='json')
        )
        return value[field]

    def set_attr(self, address: str, value: object) -> Self:
        part, field = _cfg_address(address)
        if address not in self.mutable_attributes:
            raise ValueError(f'Immutable configuration attribute: {address}')
        data = units.revalidation_dump(self)
        section = cast(dict[str, object], data[part])
        section[field] = value
        return type(self)(**data)

    def _configure_keys(self) -> None:
        fields_set = set(self.model_fields_set)
        record_keys = self.keys.record_keys
        record_key_all_apps = self.keys.record_key_all_apps

        if self.console.gui:
            record_keys = record_keys or RecordKeys.all
            record_key_all_apps = record_key_all_apps or False
            if record_key_all_apps:
                raise ValueError('record_key_all_apps is unavailable with the GUI')
        else:
            record_keys = record_keys or RecordKeys.press
            record_key_all_apps = record_key_all_apps or False
            if record_key_all_apps and not _pynput_available():
                raise ValueError('record_key_all_apps requires pynput')
            if record_keys == RecordKeys.all and not record_key_all_apps:
                raise ValueError(
                    'record_keys=all requires explicit record_key_all_apps=True'
                )

        keys = self.keys.model_copy(
            update={
                'record_keys': record_keys,
                'record_key_all_apps': record_key_all_apps,
            }
        )
        object.__setattr__(self, 'keys', keys)
        object.__setattr__(self, '__pydantic_fields_set__', fields_set)

    @cached_property
    def input_devices(self) -> InputDevices:
        if self.directory.files:
            return PrefixDict()

        if self.device.devices.name:
            devices = json.loads(self.device.devices.read_text())
            return get_input_devices(devices)

        return input_devices()

    @cached_property
    def aliases(self) -> Aliases:
        return Aliases(self.device.alias, self.input_devices)

    @cached_property
    def output_path_pattern(self) -> path_pattern.PathPattern:
        return self.path_pattern(
            self.directory.output_directory, media_directory='audio'
        )

    def path_pattern(
        self, output_directory: str, media_directory: str = ''
    ) -> path_pattern.PathPattern:
        excluded = self.aliases.to_tracks(self.selection.exclude, allow_missing=True)
        included = self.aliases.to_tracks(self.selection.include, allow_missing=True)
        selected_devices = (
            sum(
                any(source_track(input_device, excluded, included))
                for input_device in self.input_devices.values()
            )
            if included or not self.selection.include
            else 0
        )
        short_file_names = self.directory.short_file_names and selected_devices == 1
        return path_pattern.PathPattern(
            output_directory, short_file_names, media_directory=media_directory
        )

    @cached_property
    def device_profiles(self) -> dict[str, dict[str, object]]:
        path = self.device.profiles
        if not path.name:
            return {}
        if not path.exists():
            raise ValueError(f'{path} does not exist')
        data = json.loads(path.read_text())
        if not data:
            raise ValueError(f'{path} contains no profiles')
        if not isinstance(data, dict):
            raise ValueError(f'{path} must contain a JSON object')

        profiles: dict[str, dict[str, object]] = {}
        for name, values in data.items():
            if not isinstance(name, str) or not isinstance(values, dict):
                raise ValueError(f'{path} must map device names to objects')
            profiles[name] = values
        return profiles

    def with_device_profile(self, source_name: str) -> Self:
        values = self.device_profiles.get(source_name)
        if not values:
            return self

        data = units.revalidation_dump(self)
        for field, value in values.items():
            if field in CFG_PARTS:
                if not isinstance(value, dict):
                    raise ValueError(f'Profile section {field} must be an object')
                section = cast(dict[str, object], data[field])
                data[field] = section | value
            elif field in FLAT_FIELDS:
                section = cast(dict[str, object], data[FLAT_FIELDS[field]])
                section[field] = value
            else:
                raise ValueError(f'Unknown profile field: {field}')
        return type(self)(**data)

    def reload_device_profiles(self) -> Self:
        """Validate a replacement snapshot without changing this configuration."""
        previous = self.device_profiles
        candidate = self.model_copy()
        candidate.__dict__.pop('device_profiles', None)
        names = previous.keys() | candidate.device_profiles.keys()
        for name in sorted(names):
            before = self.with_device_profile(name).model_dump()
            after = candidate.with_device_profile(name).model_dump()
            for part in CFG_PARTS:
                for field, value in before[part].items():
                    address = f'{part}.{field}'
                    if (
                        address not in self.mutable_attributes
                        and value != after[part][field]
                    ):
                        raise ValueError(
                            f'Profile {name}: startup-only setting changed: {address}'
                        )
        return candidate

    @cached_property
    def metadata_dict(self) -> dict[str, str]:
        return metadata.to_dict(self.audio.metadata)

    @cached_property
    def times(self) -> time_settings.TimeSettings[float]:
        fields = time_settings.TimeSettings.model_fields
        d = {k: getattr(self.recording, k) for k in fields}
        return time_settings.TimeSettings(**d)


def _mutable_attributes(model_type: type[BaseModel], prefix: str = '') -> list[str]:
    result: list[str] = []
    for name, field in model_type.model_fields.items():
        address = f'{prefix}.{name}' if prefix else name
        annotation = field.annotation
        if isinstance(annotation, type) and issubclass(annotation, BaseModel):
            result.extend(_mutable_attributes(annotation, address))
        elif Mutable in field.metadata:
            result.append(address)
    return result


def _cfg_address(address: str) -> tuple[str, str]:
    part, separator, field = address.partition('.')
    if not separator or not part or not field or '.' in field:
        raise ValueError(f'Invalid configuration address: {address}')
    if part not in CFG_MODEL_TYPES or field not in CFG_MODEL_TYPES[part].model_fields:
        raise ValueError(f'Unknown configuration address: {address}')
    return part, field


def _pynput_available() -> bool:
    return find_spec('pynput') is not None
