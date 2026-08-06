import json
from pathlib import Path

from reccy import renderers
from reccy.models import DaemonMetadata, ServicePaths

from . import models
from .paths import service_paths
from .spec import RECS_SERVICE


def metadata(
    executable: Path,
    platform: models.Platform,
    recording_args: list[str],
    paths: models.ServicePaths | None = None,
) -> models.DaemonMetadata:
    paths = paths or service_paths(platform)
    return service_metadata(executable, platform, daemon_args(recording_args), paths)


def service_metadata(
    executable: Path,
    platform: models.Platform,
    daemon_argv: list[str],
    paths: models.ServicePaths,
) -> models.DaemonMetadata:
    return models.DaemonMetadata(
        argv=daemon_argv,
        executable=executable,
        platform=platform,
        gui_endpoint=str(paths.gui_endpoint),
    )


def daemon_args(recording_args: list[str]) -> list[str]:
    if '--silent' in recording_args or '-s' in recording_args:
        return recording_args
    return ['--silent', *recording_args]


def metadata_json(value: models.DaemonMetadata) -> str:
    return json.dumps(value.model_dump(mode='json'), indent=2) + '\n'


def macos_launch_agent(
    value: models.DaemonMetadata,
    paths: models.ServicePaths,
    service: models.ServiceSpec = RECS_SERVICE,
) -> models.ServiceDefinition:
    return renderers.macos_launch_agent(
        _reccy_metadata(value), _reccy_paths(paths), service
    )


def linux_systemd_unit(
    value: models.DaemonMetadata,
    paths: models.ServicePaths,
    service: models.ServiceSpec = RECS_SERVICE,
) -> models.ServiceDefinition:
    return renderers.linux_systemd_unit(
        _reccy_metadata(value), _reccy_paths(paths), service
    )


def linux_xdg_autostart(
    value: models.DaemonMetadata,
    home: Path | None = None,
    service: models.ServiceSpec = RECS_SERVICE,
) -> models.ServiceDefinition:
    home = home or Path.home()
    return renderers.linux_xdg_autostart(_reccy_metadata(value), home, service)


def windows_task(
    value: models.DaemonMetadata,
    paths: models.ServicePaths,
    service: models.ServiceSpec = RECS_SERVICE,
) -> models.WindowsTaskDefinition:
    return renderers.windows_task(_reccy_metadata(value), _reccy_paths(paths), service)


def _reccy_metadata(value: models.DaemonMetadata) -> DaemonMetadata:
    return DaemonMetadata(
        version=value.version,
        argv=value.argv,
        executable=value.executable,
        platform=value.platform,
        control_endpoint=value.gui_endpoint,
    )


def _reccy_paths(value: models.ServicePaths) -> ServicePaths:
    return ServicePaths(
        metadata=value.metadata,
        service=value.service,
        status=value.status,
        stdout_log=value.stdout_log,
        stderr_log=value.stderr_log,
        control_endpoint=value.gui_endpoint,
    )
