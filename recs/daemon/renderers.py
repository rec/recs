import json
from pathlib import Path

from reccy import models, renderers

from .models import ServicePaths
from .paths import service_paths
from .spec import RECS_SERVICE


def metadata(
    platform: models.Platform,
    recording_args: list[str],
    paths: ServicePaths | None = None,
) -> models.DaemonMetadata:
    paths = paths or service_paths(platform)
    return service_metadata(platform, daemon_args(recording_args), paths)


def service_metadata(
    platform: models.Platform,
    daemon_argv: list[str],
    paths: ServicePaths,
) -> models.DaemonMetadata:
    return renderers.service_metadata(
        platform, 'recs', daemon_argv, _reccy_paths(paths)
    )


def daemon_args(recording_args: list[str]) -> list[str]:
    if '--silent' in recording_args or '-s' in recording_args:
        return recording_args
    return ['--silent', *recording_args]


def metadata_json(value: models.DaemonMetadata) -> str:
    return json.dumps(value.model_dump(mode='json'), indent=2) + '\n'


def macos_launch_agent(
    value: models.DaemonMetadata,
    paths: ServicePaths,
    service: models.ServiceSpec = RECS_SERVICE,
) -> models.ServiceDefinition:
    return renderers.macos_launch_agent(value, _reccy_paths(paths), service)


def linux_systemd_unit(
    value: models.DaemonMetadata,
    paths: ServicePaths,
    service: models.ServiceSpec = RECS_SERVICE,
) -> models.ServiceDefinition:
    return renderers.linux_systemd_unit(value, _reccy_paths(paths), service)


def linux_xdg_autostart(
    value: models.DaemonMetadata,
    home: Path | None = None,
    service: models.ServiceSpec = RECS_SERVICE,
) -> models.ServiceDefinition:
    home = home or Path.home()
    return renderers.linux_xdg_autostart(value, home, service)


def windows_task(
    value: models.DaemonMetadata,
    paths: ServicePaths,
    service: models.ServiceSpec = RECS_SERVICE,
) -> models.WindowsTaskDefinition:
    return renderers.windows_task(value, _reccy_paths(paths), service)


def _reccy_paths(value: ServicePaths) -> models.ServicePaths:
    return models.ServicePaths(
        metadata=value.metadata,
        service=value.service,
        status=value.status,
        log=value.log,
        control_endpoint=value.gui_endpoint,
    )
