import os
import sys
from pathlib import Path

from .models import Platform, ServicePaths


def current_platform() -> Platform:
    if sys.platform == 'darwin':
        return Platform.macos
    if sys.platform == 'win32':
        return Platform.windows
    return Platform.linux


def service_paths(platform: Platform, home: Path | None = None) -> ServicePaths:
    home = home or Path.home()
    if platform == Platform.macos:
        return ServicePaths(
            metadata=home / '.config/recs/daemon.json',
            service=home / 'Library/LaunchAgents/com.swirly.recs.plist',
            stdout_log=home / 'Library/Logs/recs/recs.out.log',
            stderr_log=home / 'Library/Logs/recs/recs.err.log',
            gui_endpoint=home / '.local/state/recs/gui.sock',
        )
    if platform == Platform.windows:
        appdata = Path(os.environ.get('APPDATA', home / 'AppData/Roaming'))
        local = Path(os.environ.get('LOCALAPPDATA', home / 'AppData/Local'))
        return ServicePaths(
            metadata=appdata / 'recs/daemon.json',
            service=appdata / 'recs/recs-scheduled-task.json',
            stdout_log=local / 'recs/logs/recs.out.log',
            stderr_log=local / 'recs/logs/recs.err.log',
            gui_endpoint=r'\\.\pipe\recs',
        )
    return ServicePaths(
        metadata=home / '.config/recs/daemon.json',
        service=home / '.config/systemd/user/recs.service',
        stdout_log=home / '.local/state/recs/recs.out.log',
        stderr_log=home / '.local/state/recs/recs.err.log',
        gui_endpoint=home / '.local/state/recs/gui.sock',
    )
