import json
import subprocess as sp
from pathlib import Path

from . import paths, renderers
from .models import DaemonMetadata, Platform, ServiceDefinition, StatusResult


class ServiceController:
    def __init__(
        self,
        platform: Platform,
        home: Path | None = None,
        runner: object | None = None,
    ) -> None:
        self.platform = platform
        self.paths = paths.service_paths(platform, home)
        self.runner = runner or sp.run

    def install(self, metadata: DaemonMetadata) -> StatusResult:
        self._write_metadata(metadata)
        if self.platform == Platform.macos:
            self._write_definition(renderers.macos_launch_agent(metadata, self.paths))
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
            self._write_definition(renderers.linux_systemd_unit(metadata, self.paths))
            self._run(['systemctl', '--user', 'daemon-reload'])
            self._run(['systemctl', '--user', 'enable', 'recs.service'])
            self._run(['systemctl', '--user', 'start', 'recs.service'])
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
                    "Unregister-ScheduledTask -TaskName 'recs' -Confirm:$false",
                ],
                check=False,
            )
        else:
            self._run(['systemctl', '--user', 'stop', 'recs.service'], check=False)
            self._run(['systemctl', '--user', 'disable', 'recs.service'], check=False)
            self._run(['systemctl', '--user', 'daemon-reload'], check=False)

        for path in [self.paths.service, self.paths.metadata]:
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
                    "Start-ScheduledTask -TaskName 'recs'",
                ]
            )
        else:
            self._run(['systemctl', '--user', 'start', 'recs.service'])
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
                    "Stop-ScheduledTask -TaskName 'recs'",
                ]
            )
        else:
            self._run(['systemctl', '--user', 'stop', 'recs.service'])
        return StatusResult(installed=True, running=False)

    def restart(self) -> StatusResult:
        self.stop()
        return self.start()

    def status(self) -> StatusResult:
        installed = self.paths.metadata.exists() or self.paths.service.exists()
        if self.platform == Platform.macos:
            result = self._run(
                ['launchctl', 'print', f'gui/{_uid()}/com.swirly.recs'],
                check=False,
                capture_output=True,
            )
        elif self.platform == Platform.windows:
            result = self._run(
                [
                    'powershell',
                    '-NoProfile',
                    '-Command',
                    "Get-ScheduledTask -TaskName 'recs'",
                ],
                check=False,
                capture_output=True,
            )
        else:
            result = self._run(
                ['systemctl', '--user', 'is-active', 'recs.service'],
                check=False,
                capture_output=True,
            )
        return StatusResult(
            installed=installed,
            running=result.returncode == 0,
            details=(result.stdout or result.stderr or '').strip(),
        )

    def _write_metadata(self, metadata: DaemonMetadata) -> None:
        self.paths.metadata.parent.mkdir(parents=True, exist_ok=True)
        self.paths.metadata.write_text(renderers.metadata_json(metadata))

    def _write_definition(self, definition: ServiceDefinition) -> None:
        definition.path.parent.mkdir(parents=True, exist_ok=True)
        definition.path.write_text(definition.content)
        self.paths.stdout_log.parent.mkdir(parents=True, exist_ok=True)

    def _write_windows_task(self, metadata: DaemonMetadata) -> None:
        task = renderers.windows_task(metadata, self.paths)
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
        "$task = Get-Content "
        + _powershell_string(path)
        + " | ConvertFrom-Json; "
        + "$action = New-ScheduledTaskAction -Execute $task.executable "
        + "-Argument $task.argument_string "
        + "-WorkingDirectory $task.working_directory; "
        + "$trigger = New-ScheduledTaskTrigger -AtLogOn; "
        + "$settings = New-ScheduledTaskSettingsSet -RestartCount 3 "
        + "-RestartInterval (New-TimeSpan -Minutes 1); "
        + "Register-ScheduledTask -TaskName $task.task_name "
        + "-Action $action -Trigger $trigger -Settings $settings -Force"
    )


def _powershell_string(path: Path) -> str:
    return "'" + str(path).replace("'", "''") + "'"


def _uid() -> int:
    try:
        import os

        return os.getuid()
    except AttributeError:
        return 0
