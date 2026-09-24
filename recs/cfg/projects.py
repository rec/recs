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
from recs.cfg.cfg import Cfg

from . import cli, run_cli, settings
from .track_names import SourceTrackNames


class Project(BaseModel, frozen=True):
    cfg: Cfg
    track_names: SourceTrackNames = Field(default_factory=dict)
    tracks: dict[str, list[settings.TrackSettings]] = Field(default_factory=dict)

    model_config = ConfigDict(extra='forbid')


class ProjectCommand(BaseModel, frozen=True):
    pass


class Save(ProjectCommand):
    name: Annotated[str, tyro.conf.Positional]

    replace: bool = False

    recs_options: Annotated[list[str], tyro.conf.Positional] = Field(
        default_factory=list
    )


class Use(ProjectCommand):
    name: Annotated[str, tyro.conf.Positional]

    recs_options: Annotated[list[str], tyro.conf.Positional] = Field(
        default_factory=list
    )


class Show(ProjectCommand):
    name: Annotated[str, tyro.conf.Positional]


class Switch(ProjectCommand):
    """Switch a running recorder to a project, or omit NAME for the default."""

    names: Annotated[list[str], tyro.conf.Positional] = Field(default_factory=list)


class ListProjects(ProjectCommand):
    pass


class Delete(ProjectCommand):
    name: Annotated[str, tyro.conf.Positional]


def save(name: str, project: Project, *, replace: bool = False) -> Path:
    path = project_path(name)
    if path.exists() and not replace:
        raise RecsError(f'Recording project already exists: {name}')
    try:
        configuration_settings.write_json_model(path, project, indent=2)
    except OSError as e:
        raise RecsError(f'Could not save recording project {name}: {e}') from None
    return path


def load(name: str) -> Project:
    path = project_path(name)
    try:
        return Project.model_validate_json(path.read_text())
    except FileNotFoundError:
        raise RecsError(f'Unknown recording project: {name}') from None
    except (OSError, ValidationError, json.JSONDecodeError) as e:
        raise RecsError(f'Could not read recording project {name}: {e}') from None


def configured(name: str, arguments: list[str]) -> settings.LoadedSettings:
    project = load(name)
    cfg = tyro.cli(cli.CliCfg, default=project.cfg, args=arguments, prog='recs')
    return settings.load(
        cfg,
        run_cli.cli_overrides(arguments),
        project_name=name,
        track_names=project.track_names,
        tracks=project.tracks,
    )


def main(argv: list[str]) -> int:
    command = tyro.extras.subcommand_cli_from_dict(
        COMMANDS,
        args=argv,
        prog='recs project',
        description=(
            'Save and use recording projects. '
            'These differ from the per-device JSON defaults loaded by --profiles.'
        ),
    )
    if isinstance(command, Save):
        current = settings.load(Cfg(save_settings=True))
        cfg = tyro.cli(
            cli.CliCfg,
            default=current.cfg,
            args=command.recs_options,
            prog='recs project save',
        )
        path = save(
            command.name,
            Project(
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
    if isinstance(command, Switch):
        from recs.daemon import control_cli

        if len(command.names) > 1:
            raise RecsError('project switch accepts at most one project name')
        arguments = ['project-switch']
        arguments.extend(command.names)
        return control_cli.main(arguments)
    if isinstance(command, ListProjects):
        for path in sorted(projects_directory().glob('*.json')):
            print(path.stem)
        return 0
    if isinstance(command, Delete):
        path = project_path(command.name)
        if not path.exists():
            raise RecsError(f'Unknown recording project: {command.name}')
        path.unlink()
        return 0
    raise RecsError(f'Unsupported project command: {type(command).__name__}')


def project_argument(arguments: list[str]) -> tuple[str | None, list[str]]:
    result: list[str] = []
    name: str | None = None
    i = 0
    while i < len(arguments):
        argument = arguments[i]
        if argument == '--project-name':
            if name is not None or i + 1 == len(arguments):
                raise RecsError('--project-name requires exactly one project name')
            name = arguments[i + 1]
            i += 2
            continue
        if argument.startswith('--project-name='):
            if name is not None:
                raise RecsError('--project-name requires exactly one project name')
            name = argument.split('=', 1)[1]
            i += 1
            continue
        result.append(argument)
        i += 1
    return name, result


def project_path(name: str) -> Path:
    if not name or name in {'.', '..', '-default-'} or Path(name).name != name:
        raise RecsError(f'Invalid recording project name: {name!r}')
    return projects_directory() / f'{name}.json'


def projects_directory() -> Path:
    if sys.platform == 'win32':
        appdata = Path(os.environ.get('APPDATA', Path.home() / 'AppData/Roaming'))
        return appdata / 'recs' / _projects_directory_name()
    return Path.home() / '.config/recs' / _projects_directory_name()


def _projects_directory_name() -> str:
    return 'daemon-projects' if os.environ.get('RECS_DAEMON') == '1' else 'projects'


COMMANDS: dict[str, Callable[..., ProjectCommand]] = {
    'save': Save,
    'use': Use,
    'show': Show,
    'switch': Switch,
    'list': ListProjects,
    'delete': Delete,
}
