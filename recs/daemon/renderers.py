import json
import plistlib
import shlex
import subprocess as sp
from pathlib import Path

from .models import (
    DaemonMetadata,
    Platform,
    ServiceDefinition,
    ServicePaths,
    WindowsTaskDefinition,
)

TASK_NAME = 'recs'
LAUNCHD_LABEL = 'com.swirly.recs'


def metadata(
    executable: Path,
    platform: Platform,
    recording_args: list[str],
) -> DaemonMetadata:
    return DaemonMetadata(
        argv=daemon_args(recording_args),
        executable=executable,
        platform=platform,
    )


def daemon_args(recording_args: list[str]) -> list[str]:
    if '--silent' in recording_args or '-s' in recording_args:
        return recording_args
    return ['--silent', *recording_args]


def metadata_json(value: DaemonMetadata) -> str:
    return json.dumps(value.model_dump(mode='json'), indent=2) + '\n'


def macos_launch_agent(
    value: DaemonMetadata, paths: ServicePaths
) -> ServiceDefinition:
    plist = {
        'KeepAlive': True,
        'Label': LAUNCHD_LABEL,
        'ProgramArguments': [str(value.executable), *value.argv],
        'RunAtLoad': True,
        'StandardErrorPath': str(paths.stderr_log),
        'StandardOutPath': str(paths.stdout_log),
        'WorkingDirectory': str(Path.home()),
    }
    content = plistlib.dumps(plist, sort_keys=True).decode()
    return ServiceDefinition(path=paths.service, content=content)


def linux_systemd_unit(
    value: DaemonMetadata, paths: ServicePaths
) -> ServiceDefinition:
    command = shlex.join([str(value.executable), *value.argv])
    content = '\n'.join(
        [
            '[Unit]',
            'Description=recs background recorder',
            'After=default.target',
            '',
            '[Service]',
            f'ExecStart={command}',
            'Restart=always',
            'RestartSec=5',
            'WorkingDirectory=%h',
            f'StandardOutput=append:{paths.stdout_log}',
            f'StandardError=append:{paths.stderr_log}',
            '',
            '[Install]',
            'WantedBy=default.target',
            '',
        ]
    )
    return ServiceDefinition(path=paths.service, content=content)


def linux_xdg_autostart(
    value: DaemonMetadata, home: Path | None = None
) -> ServiceDefinition:
    home = home or Path.home()
    command = shlex.join([str(value.executable), *value.argv])
    path = home / '.config/autostart/recs.desktop'
    content = '\n'.join(
        [
            '[Desktop Entry]',
            'Type=Application',
            'Name=recs',
            'Comment=recs background recorder',
            f'Exec={command}',
            'Terminal=false',
            'X-GNOME-Autostart-enabled=true',
            '',
        ]
    )
    return ServiceDefinition(path=path, content=content)


def windows_task(
    value: DaemonMetadata, paths: ServicePaths
) -> WindowsTaskDefinition:
    return WindowsTaskDefinition(
        task_name=TASK_NAME,
        executable=value.executable,
        arguments=value.argv,
        argument_string=sp.list2cmdline(value.argv),
        working_directory=Path.home(),
        stdout_log=paths.stdout_log,
        stderr_log=paths.stderr_log,
    )
