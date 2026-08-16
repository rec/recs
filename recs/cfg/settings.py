import json
import os
import sys
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from reccy import settings

from recs.base.errors import RecsError

from .cfg import Cfg
from .track_names import SourceTrackNames, validate_track_names


class TrackSettings(BaseModel):
    channels: list[int]

    model_config = ConfigDict(frozen=True)


class Settings(BaseModel):
    attributes: dict[str, object] = Field(default_factory=dict)
    track_names: SourceTrackNames = Field(default_factory=dict)
    tracks: dict[str, list[TrackSettings]] = Field(default_factory=dict)

    model_config = ConfigDict(frozen=True)


class LoadedSettings(BaseModel):
    cfg: Cfg
    track_names: SourceTrackNames = Field(default_factory=dict)
    tracks: dict[str, list[TrackSettings]] = Field(default_factory=dict)

    model_config = ConfigDict(frozen=True)


def load(cfg: Cfg, overrides: set[str] | None = None) -> LoadedSettings:
    if not cfg.save_settings:
        return LoadedSettings(cfg=cfg)
    overrides = overrides or set()
    path = settings_path()
    if not path.exists():
        return LoadedSettings(cfg=cfg)
    try:
        settings = Settings.model_validate_json(path.read_text())
    except (OSError, ValidationError, json.JSONDecodeError) as e:
        raise RecsError(f'Could not read settings from {path}: {e}') from None
    try:
        for address, value in settings.attributes.items():
            if address in overrides:
                continue
            cfg = cfg.set_attr(address, value)
        track_names = validate_track_names(settings.track_names)
    except ValueError as e:
        raise RecsError(f'Invalid settings in {path}: {e}') from None
    return LoadedSettings(
        cfg=cfg,
        track_names={source: dict(names) for source, names in track_names.items()},
        tracks=settings.tracks,
    )


def save(
    cfg: Cfg,
    track_names: SourceTrackNames,
    tracks: dict[str, list[TrackSettings]],
) -> None:
    attributes = {address: cfg.get_attr(address) for address in cfg.mutable_attributes}
    saved_settings = Settings(
        attributes=attributes,
        track_names=track_names,
        tracks=tracks,
    )
    path = settings_path()
    try:
        settings.write_json_model(path, saved_settings, indent=2)
    except OSError as e:
        raise RecsError(f'Could not save settings to {path}: {e}') from None


def settings_path() -> Path:
    if sys.platform == 'win32':
        appdata = Path(os.environ.get('APPDATA', Path.home() / 'AppData/Roaming'))
        return appdata / 'recs/settings.json'
    return Path.home() / '.config/recs/settings.json'
