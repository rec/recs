import json
import os
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Annotated

import tyro
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from reccy.configuration import settings as configuration_settings

from recs.base.errors import RecsError

from . import cli, run_cli, settings
from .cfg import Cfg
from .track_names import SourceTrackNames


class SetupProfile(BaseModel, frozen=True):
    cfg: Cfg
    track_names: SourceTrackNames = Field(default_factory=dict)
    tracks: dict[str, list[settings.TrackSettings]] = Field(default_factory=dict)

    model_config = ConfigDict(extra='forbid')


class ProfileCommand(BaseModel, frozen=True):
    pass


class Save(ProfileCommand):
    name: Annotated[str, tyro.conf.Positional]

    replace: bool = False

    recs_options: Annotated[list[str], tyro.conf.Positional] = Field(
        default_factory=list
    )


class Use(ProfileCommand):
    name: Annotated[str, tyro.conf.Positional]

    recs_options: Annotated[list[str], tyro.conf.Positional] = Field(
        default_factory=list
    )


class Show(ProfileCommand):
    name: Annotated[str, tyro.conf.Positional]


class ListProfiles(ProfileCommand):
    pass


class Delete(ProfileCommand):
    name: Annotated[str, tyro.conf.Positional]


def save(name: str, profile: SetupProfile, *, replace: bool = False) -> Path:
    path = profile_path(name)
    if path.exists() and not replace:
        raise RecsError(f'Recording setup already exists: {name}')
    try:
        configuration_settings.write_json_model(path, profile, indent=2)
    except OSError as e:
        raise RecsError(f'Could not save recording setup {name}: {e}') from None
    return path


def load(name: str) -> SetupProfile:
    path = profile_path(name)
    try:
        return SetupProfile.model_validate_json(path.read_text())
    except FileNotFoundError:
        raise RecsError(f'Unknown recording setup: {name}') from None
    except (OSError, ValidationError, json.JSONDecodeError) as e:
        raise RecsError(f'Could not read recording setup {name}: {e}') from None


def configured(name: str, arguments: list[str]) -> settings.LoadedSettings:
    profile = load(name)
    cfg = tyro.cli(cli.CliCfg, default=profile.cfg, args=arguments, prog='recs')
    return settings.LoadedSettings(
        cfg=cfg,
        track_names=profile.track_names,
        tracks=profile.tracks,
    )


def main(argv: list[str]) -> int:
    command = tyro.extras.subcommand_cli_from_dict(
        COMMANDS,
        args=argv,
        prog='recs profile',
        description='Save and use named recording setups.',
    )
    if isinstance(command, Save):
        current = settings.load(Cfg(save_settings=True))
        cfg = tyro.cli(
            cli.CliCfg,
            default=current.cfg,
            args=command.recs_options,
            prog='recs profile save',
        )
        path = save(
            command.name,
            SetupProfile(
                cfg=cfg,
                track_names=current.track_names,
                tracks=current.tracks,
            ),
            replace=command.replace,
        )
        print(path)
        return 0
    if isinstance(command, Use):
        loaded = configured(command.name, command.recs_options)
        run_cli.run_cli(loaded.cfg, loaded)
        return 0
    if isinstance(command, Show):
        print(load(command.name).model_dump_json(indent=2))
        return 0
    if isinstance(command, ListProfiles):
        for path in sorted(profiles_directory().glob('*.json')):
            print(path.stem)
        return 0
    if isinstance(command, Delete):
        path = profile_path(command.name)
        if not path.exists():
            raise RecsError(f'Unknown recording setup: {command.name}')
        path.unlink()
        return 0
    raise RecsError(f'Unsupported profile command: {type(command).__name__}')


def profile_argument(arguments: list[str]) -> tuple[str | None, list[str]]:
    result: list[str] = []
    name: str | None = None
    i = 0
    while i < len(arguments):
        argument = arguments[i]
        if argument == '--profile':
            if name is not None or i + 1 == len(arguments):
                raise RecsError('--profile requires exactly one setup name')
            name = arguments[i + 1]
            i += 2
            continue
        if argument.startswith('--profile='):
            if name is not None:
                raise RecsError('--profile requires exactly one setup name')
            name = argument.split('=', 1)[1]
            i += 1
            continue
        result.append(argument)
        i += 1
    return name, result


def profile_path(name: str) -> Path:
    if not name or name in {'.', '..'} or Path(name).name != name:
        raise RecsError(f'Invalid recording setup name: {name!r}')
    return profiles_directory() / f'{name}.json'


def profiles_directory() -> Path:
    if sys.platform == 'win32':
        appdata = Path(os.environ.get('APPDATA', Path.home() / 'AppData/Roaming'))
        return appdata / 'recs/profiles'
    return Path.home() / '.config/recs/profiles'


COMMANDS: dict[str, Callable[..., ProfileCommand]] = {
    'save': Save,
    'use': Use,
    'show': Show,
    'list': ListProfiles,
    'delete': Delete,
}
