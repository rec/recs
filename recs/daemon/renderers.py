import json
from pathlib import Path

from reccy import renderers as reccy_renderers
from reccy.models import DaemonMetadata as ReccyDaemonMetadata
from reccy.models import ServicePaths as ReccyServicePaths

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
    return reccy_renderers.macos_launch_agent(
        _reccy_metadata(value), _reccy_paths(paths), service
    )


def linux_systemd_unit(
    value: DaemonMetadata,
    paths: ServicePaths,
    service: ServiceSpec = RECS_SERVICE,
) -> ServiceDefinition:
    return reccy_renderers.linux_systemd_unit(
        _reccy_metadata(value), _reccy_paths(paths), service
    )


def linux_xdg_autostart(
    value: DaemonMetadata,
    home: Path | None = None,
    service: ServiceSpec = RECS_SERVICE,
) -> ServiceDefinition:
    home = home or Path.home()
    return reccy_renderers.linux_xdg_autostart(_reccy_metadata(value), home, service)


def windows_task(
    value: DaemonMetadata,
    paths: ServicePaths,
    service: ServiceSpec = RECS_SERVICE,
) -> WindowsTaskDefinition:
    return reccy_renderers.windows_task(
        _reccy_metadata(value), _reccy_paths(paths), service
    )


def _reccy_metadata(value: DaemonMetadata) -> ReccyDaemonMetadata:
    return ReccyDaemonMetadata(
        version=value.version,
        argv=value.argv,
        executable=value.executable,
        platform=value.platform,
        control_endpoint=value.gui_endpoint,
    )


def _reccy_paths(value: ServicePaths) -> ReccyServicePaths:
    return ReccyServicePaths(
        metadata=value.metadata,
        service=value.service,
        status=value.status,
        stdout_log=value.stdout_log,
        stderr_log=value.stderr_log,
        control_endpoint=value.gui_endpoint,
    )
