import json
import os
import subprocess as sp
import typing as t
from pathlib import Path

from pydantic import ValidationError

from . import paths, renderers
from .models import (
    DaemonMetadata,
    DaemonStatus,
    Platform,
    ServiceDefinition,
    ServiceSpec,
    StatusResult,
)
from .spec import RECS_SERVICE


class ServiceController:
    def __init__(
        self,
        platform: Platform,
        home: Path | None = None,
        runner: t.Callable[..., sp.CompletedProcess[str]] | None = None,
        service: ServiceSpec = RECS_SERVICE,
    ) -> None:
        self.platform = platform
        self.service = service
        self.paths = paths.service_paths(platform, home, service)
        self.runner = runner or sp.run

    def install(self, metadata: DaemonMetadata) -> StatusResult:
        self._write_metadata(metadata)
        if self.platform == Platform.macos:
            self._write_definition(
                renderers.macos_launch_agent(metadata, self.paths, self.service)
            )
            self._run(
                [
                    'launchctl',
                    'bootstrap',
                    f'gui/{_uid()}',
                    str(self.paths.service),
                ]
            )
        elif self.platform == Platform.windows:
            self._write_windows_task(metadata)
            self._run(
                [
                    'powershell',
                    '-NoProfile',
                    '-Command',
                    _register_windows_task_command(self.paths.service),
                ]
            )
        else:
            self._write_definition(
                renderers.linux_systemd_unit(metadata, self.paths, self.service)
            )
            self._run(['systemctl', '--user', 'daemon-reload'])
            self._run(['systemctl', '--user', 'enable', self.service.systemd_unit])
            self._run(['systemctl', '--user', 'start', self.service.systemd_unit])
        return StatusResult(installed=True, running=True)

    def uninstall(self) -> StatusResult:
        if self.platform == Platform.macos:
            self._run(
                [
                    'launchctl',
                    'bootout',
                    f'gui/{_uid()}',
                    str(self.paths.service),
                ],
                check=False,
            )
        elif self.platform == Platform.windows:
            self._run(
                [
                    'powershell',
                    '-NoProfile',
                    '-Command',
                    _unregister_windows_task_command(self.service.name),
                ],
                check=False,
            )
        else:
            self._run(
                ['systemctl', '--user', 'stop', self.service.systemd_unit],
                check=False,
            )
            self._run(
                ['systemctl', '--user', 'disable', self.service.systemd_unit],
                check=False,
            )
            self._run(['systemctl', '--user', 'daemon-reload'], check=False)

        for path in [self.paths.service, self.paths.metadata, self.paths.status]:
            path.unlink(missing_ok=True)
        return StatusResult(installed=False, running=False)

    def start(self) -> StatusResult:
        if self.platform == Platform.macos:
            self._run(
                [
                    'launchctl',
                    'bootstrap',
                    f'gui/{_uid()}',
                    str(self.paths.service),
                ]
            )
        elif self.platform == Platform.windows:
            self._run(
                [
                    'powershell',
                    '-NoProfile',
                    '-Command',
                    _start_windows_task_command(self.service.name),
                ]
            )
        else:
            self._run(['systemctl', '--user', 'start', self.service.systemd_unit])
        return StatusResult(installed=True, running=True)

    def stop(self) -> StatusResult:
        if self.platform == Platform.macos:
            self._run(
                ['launchctl', 'bootout', f'gui/{_uid()}', str(self.paths.service)]
            )
        elif self.platform == Platform.windows:
            self._run(
                [
                    'powershell',
                    '-NoProfile',
                    '-Command',
                    _stop_windows_task_command(self.service.name),
                ]
            )
        else:
            self._run(['systemctl', '--user', 'stop', self.service.systemd_unit])
        return StatusResult(installed=True, running=False)

    def restart(self) -> StatusResult:
        self.stop()
        return self.start()

    def status(self) -> StatusResult:
        installed = self.paths.metadata.exists() or self.paths.service.exists()
        if self.platform == Platform.macos:
            result = self._run(
                ['launchctl', 'print', f'gui/{_uid()}/{self.service.launchd_label}'],
                check=False,
                capture_output=True,
            )
        elif self.platform == Platform.windows:
            result = self._run(
                [
                    'powershell',
                    '-NoProfile',
                    '-Command',
                    _get_windows_task_command(self.service.name),
                ],
                check=False,
                capture_output=True,
            )
        else:
            result = self._run(
                ['systemctl', '--user', 'is-active', self.service.systemd_unit],
                check=False,
                capture_output=True,
            )
        details = (result.stdout or result.stderr or '').strip()
        status = _read_status(self.paths.status)
        if status and status.gui_ipc_error:
            details = '\n'.join(
                part
                for part in [details, f'GUI IPC error: {status.gui_ipc_error}']
                if part
            )
        return StatusResult(
            health=status,
            installed=installed,
            running=result.returncode == 0,
            details=details,
        )

    def _write_metadata(self, metadata: DaemonMetadata) -> None:
        self.paths.metadata.parent.mkdir(parents=True, exist_ok=True)
        _write_text_atomically(self.paths.metadata, renderers.metadata_json(metadata))

    def _write_definition(self, definition: ServiceDefinition) -> None:
        definition.path.parent.mkdir(parents=True, exist_ok=True)
        definition.path.write_text(definition.content)
        self.paths.stdout_log.parent.mkdir(parents=True, exist_ok=True)

    def _write_windows_task(self, metadata: DaemonMetadata) -> None:
        task = renderers.windows_task(metadata, self.paths, self.service)
        self.paths.service.parent.mkdir(parents=True, exist_ok=True)
        self.paths.service.write_text(
            json.dumps(task.model_dump(mode='json'), indent=2) + '\n'
        )
        self.paths.stdout_log.parent.mkdir(parents=True, exist_ok=True)

    def _run(
        self,
        command: list[str],
        *,
        check: bool = True,
        capture_output: bool = False,
    ) -> sp.CompletedProcess[str]:
        return self.runner(
            command,
            check=check,
            text=True,
            capture_output=capture_output,
        )


def _register_windows_task_command(path: Path) -> str:
    return (
        '$task = Get-Content '
        + _powershell_string(path)
        + ' | ConvertFrom-Json; '
        + '$action = New-ScheduledTaskAction -Execute $task.executable '
        + '-Argument $task.argument_string '
        + '-WorkingDirectory $task.working_directory; '
        + '$trigger = New-ScheduledTaskTrigger -AtLogOn; '
        + '$settings = New-ScheduledTaskSettingsSet -RestartCount 3 '
        + '-RestartInterval (New-TimeSpan -Minutes 1); '
        + 'Register-ScheduledTask -TaskName $task.task_name '
        + '-Action $action -Trigger $trigger -Settings $settings -Force'
    )


def _unregister_windows_task_command(name: str) -> str:
    task_name = _powershell_value(name)
    return f'Unregister-ScheduledTask -TaskName {task_name} -Confirm:$false'


def _start_windows_task_command(name: str) -> str:
    return f'Start-ScheduledTask -TaskName {_powershell_value(name)}'


def _stop_windows_task_command(name: str) -> str:
    return f'Stop-ScheduledTask -TaskName {_powershell_value(name)}'


def _get_windows_task_command(name: str) -> str:
    return f'Get-ScheduledTask -TaskName {_powershell_value(name)}'


def _powershell_string(path: Path) -> str:
    return "'" + str(path).replace("'", "''") + "'"


def _powershell_value(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _uid() -> int:
    try:
        import os

        return os.getuid()
    except AttributeError:
        return 0


def _write_text_atomically(path: Path, content: str) -> None:
    tmp = path.with_name(f'.{path.name}.tmp')
    with tmp.open('w') as fp:
        fp.write(content)
        fp.flush()
        os.fsync(fp.fileno())
    tmp.replace(path)


def _read_status(path: Path) -> DaemonStatus | None:
    if not path.exists():
        return None
    try:
        return DaemonStatus.model_validate_json(path.read_text())
    except ValidationError:
        return None
