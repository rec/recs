import json
import plistlib
import shlex
import subprocess as sp
from pathlib import Path

from . import paths as paths_module
from .models import (
    DaemonMetadata,
    Platform,
    ServiceDefinition,
    ServicePaths,
    ServiceSpec,
    WindowsTaskDefinition,
)
from .spec import RECS_SERVICE


def metadata(
    executable: Path,
    platform: Platform,
    recording_args: list[str],
    paths: ServicePaths | None = None,
) -> DaemonMetadata:
    paths = paths or paths_module.service_paths(platform)
    return service_metadata(executable, platform, daemon_args(recording_args), paths)


def service_metadata(
    executable: Path,
    platform: Platform,
    daemon_argv: list[str],
    paths: ServicePaths,
) -> DaemonMetadata:
    return DaemonMetadata(
        argv=daemon_argv,
        executable=executable,
        platform=platform,
        gui_endpoint=str(paths.gui_endpoint),
    )


def daemon_args(recording_args: list[str]) -> list[str]:
    if '--silent' in recording_args or '-s' in recording_args:
        return recording_args
    return ['--silent', *recording_args]


def metadata_json(value: DaemonMetadata) -> str:
    return json.dumps(value.model_dump(mode='json'), indent=2) + '\n'


def macos_launch_agent(
    value: DaemonMetadata,
    paths: ServicePaths,
    service: ServiceSpec = RECS_SERVICE,
) -> ServiceDefinition:
    plist = {
        'KeepAlive': True,
        'Label': service.launchd_label,
        'ProgramArguments': [_posix(value.executable), *value.argv],
        'RunAtLoad': True,
        'StandardErrorPath': _posix(paths.stderr_log),
        'StandardOutPath': _posix(paths.stdout_log),
        'WorkingDirectory': str(Path.home()),
        'EnvironmentVariables': {service.daemon_env_var: '1'},
    }
    content = plistlib.dumps(plist, sort_keys=True).decode()
    return ServiceDefinition(path=paths.service, content=content)


def linux_systemd_unit(
    value: DaemonMetadata,
    paths: ServicePaths,
    service: ServiceSpec = RECS_SERVICE,
) -> ServiceDefinition:
    command = shlex.join([_posix(value.executable), *value.argv])
    content = '\n'.join(
        [
            '[Unit]',
            f'Description={service.description}',
            'After=default.target',
            '',
            '[Service]',
            f'ExecStart={command}',
            f'Environment={service.daemon_env_var}=1',
            'Restart=always',
            'RestartSec=5',
            'WorkingDirectory=%h',
            f'StandardOutput=append:{_posix(paths.stdout_log)}',
            f'StandardError=append:{_posix(paths.stderr_log)}',
            '',
            '[Install]',
            'WantedBy=default.target',
            '',
        ]
    )
    return ServiceDefinition(path=paths.service, content=content)


def linux_xdg_autostart(
    value: DaemonMetadata,
    home: Path | None = None,
    service: ServiceSpec = RECS_SERVICE,
) -> ServiceDefinition:
    home = home or Path.home()
    command = shlex.join([_posix(value.executable), *value.argv])
    path = home / '.config/autostart' / service.desktop_file
    content = '\n'.join(
        [
            '[Desktop Entry]',
            'Type=Application',
            f'Name={service.display_name}',
            f'Comment={service.description}',
            f'Exec={command}',
            'Terminal=false',
            'X-GNOME-Autostart-enabled=true',
            '',
        ]
    )
    return ServiceDefinition(path=path, content=content)


def windows_task(
    value: DaemonMetadata,
    paths: ServicePaths,
    service: ServiceSpec = RECS_SERVICE,
) -> WindowsTaskDefinition:
    return WindowsTaskDefinition(
        task_name=service.name,
        executable=value.executable,
        arguments=value.argv,
        argument_string=sp.list2cmdline(value.argv),
        working_directory=Path.home(),
        stdout_log=paths.stdout_log,
        stderr_log=paths.stderr_log,
    )


def _posix(path: Path) -> str:
    return path.as_posix()
