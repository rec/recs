import json
import os
import sys
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator
from reccy.configuration import settings

from recs.base.errors import RecsError
from recs.cfg.cfg import Cfg
from recs.musicians import Musician, SourceMusician

from .track_names import SourceTrackNames, validate_track_names


class TrackSettings(BaseModel):
    channels: list[int]

    model_config = ConfigDict(frozen=True)


class Settings(BaseModel):
    attributes: dict[str, object] = Field(default_factory=dict)
    track_names: SourceTrackNames = Field(default_factory=dict)
    tracks: dict[str, list[TrackSettings]] = Field(default_factory=dict)
    musicians: dict[str, Musician] = Field(default_factory=dict)
    channel_musicians: dict[str, SourceMusician] = Field(default_factory=dict)

    @model_validator(mode='after')
    def musician_references(self) -> 'Settings':
        for name, musician in self.musicians.items():
            if name != musician.name:
                raise ValueError(f'Musician key does not match record name: {name}')
        for source, assignment in self.channel_musicians.items():
            if assignment.musician not in self.musicians:
                raise ValueError(
                    f'Source {source} references unknown musician: '
                    f'{assignment.musician}'
                )
        return self

    model_config = ConfigDict(frozen=True)


class LoadedSettings(BaseModel):
    cfg: Cfg
    track_names: SourceTrackNames = Field(default_factory=dict)
    tracks: dict[str, list[TrackSettings]] = Field(default_factory=dict)
    musicians: dict[str, Musician] = Field(default_factory=dict)
    channel_musicians: dict[str, SourceMusician] = Field(default_factory=dict)
    profile: str | None = None

    model_config = ConfigDict(frozen=True)


def load(
    cfg: Cfg,
    overrides: set[str] | None = None,
    *,
    profile: str | None = None,
    track_names: SourceTrackNames | None = None,
    tracks: dict[str, list[TrackSettings]] | None = None,
    musicians: dict[str, Musician] | None = None,
    channel_musicians: dict[str, SourceMusician] | None = None,
) -> LoadedSettings:
    track_names = track_names or {}
    tracks = tracks or {}
    musicians = musicians or {}
    channel_musicians = channel_musicians or {}
    if not cfg.save_settings:
        return LoadedSettings(
            cfg=cfg,
            track_names=track_names,
            tracks=tracks,
            musicians=musicians,
            channel_musicians=channel_musicians,
            profile=profile,
        )
    overrides = overrides or set()
    path = mutable_settings_path(profile)
    if not path.exists():
        return LoadedSettings(
            cfg=cfg,
            track_names=track_names,
            tracks=tracks,
            musicians=musicians,
            channel_musicians=channel_musicians,
            profile=profile,
        )
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
        musicians=settings.musicians,
        channel_musicians=settings.channel_musicians,
        profile=profile,
    )


def save(
    cfg: Cfg,
    track_names: SourceTrackNames,
    tracks: dict[str, list[TrackSettings]],
    *,
    profile: str | None = None,
    musicians: dict[str, Musician] | None = None,
    channel_musicians: dict[str, SourceMusician] | None = None,
) -> None:
    attributes = {
        address: cfg.get_attr(address, authored=True)
        for address in cfg.mutable_attributes
    }
    saved_settings = Settings(
        attributes=attributes,
        track_names=track_names,
        tracks=tracks,
        musicians=musicians or {},
        channel_musicians=channel_musicians or {},
    )
    path = mutable_settings_path(profile)
    try:
        settings.write_json_model(path, saved_settings, indent=2)
    except OSError as e:
        raise RecsError(f'Could not save settings to {path}: {e}') from None


def mutable_settings_path(profile: str | None = None) -> Path:
    if profile is not None:
        return profile_settings_path(profile)
    return settings_path()


def settings_path() -> Path:
    if sys.platform == 'win32':
        appdata = Path(os.environ.get('APPDATA', Path.home() / 'AppData/Roaming'))
        return appdata / 'recs/settings.json'
    return Path.home() / '.config/recs/settings.json'


def profile_settings_path(profile: str) -> Path:
    if not profile or profile in {'.', '..'} or Path(profile).name != profile:
        raise RecsError(f'Invalid recording setup name: {profile!r}')
    if sys.platform == 'win32':
        appdata = Path(os.environ.get('APPDATA', Path.home() / 'AppData/Roaming'))
        return appdata / f'recs/profile-settings/{profile}.json'
    return Path.home() / f'.config/recs/profile-settings/{profile}.json'
