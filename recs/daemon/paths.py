import os
import sys
from pathlib import Path

from .models import Platform, ServicePaths, ServiceSpec
from .spec import RECS_SERVICE


def current_platform() -> Platform:
    if sys.platform == 'darwin':
        return Platform.macos
    if sys.platform == 'win32':
        return Platform.windows
    return Platform.linux


def service_paths(
    platform: Platform,
    home: Path | None = None,
    service: ServiceSpec = RECS_SERVICE,
) -> ServicePaths:
    home = home or Path.home()
    if platform == Platform.macos:
        return ServicePaths(
            metadata=home / '.config' / service.metadata_file,
            service=home / 'Library/LaunchAgents' / f'{service.launchd_label}.plist',
            status=home / '.local/state' / service.status_file,
            stdout_log=home / 'Library/Logs' / service.stdout_log_file,
            stderr_log=home / 'Library/Logs' / service.stderr_log_file,
            gui_endpoint=home / '.local/state' / service.socket_file,
        )
    if platform == Platform.windows:
        appdata = Path(os.environ.get('APPDATA', home / 'AppData/Roaming'))
        local = Path(os.environ.get('LOCALAPPDATA', home / 'AppData/Local'))
        return ServicePaths(
            metadata=appdata / service.metadata_file,
            service=appdata / service.scheduled_task_file,
            status=local / service.status_file,
            stdout_log=local / service.name / 'logs' / f'{service.name}.out.log',
            stderr_log=local / service.name / 'logs' / f'{service.name}.err.log',
            gui_endpoint=service.windows_pipe,
        )
    return ServicePaths(
        metadata=home / '.config' / service.metadata_file,
        service=home / '.config/systemd/user' / service.systemd_unit,
        status=home / '.local/state' / service.status_file,
        stdout_log=home / '.local/state' / service.stdout_log_file,
        stderr_log=home / '.local/state' / service.stderr_log_file,
        gui_endpoint=home / '.local/state' / service.socket_file,
    )
