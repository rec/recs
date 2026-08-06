from pathlib import Path

from reccy import paths as reccy_paths

from .models import Platform, ServicePaths, ServiceSpec
from .spec import RECS_SERVICE


def current_platform() -> Platform:
    return reccy_paths.current_platform()


def service_paths(
    platform: Platform,
    home: Path | None = None,
    service: ServiceSpec = RECS_SERVICE,
) -> ServicePaths:
    value = reccy_paths.service_paths(service, platform, home)
    return ServicePaths(
        metadata=value.metadata,
        service=value.service,
        status=value.status,
        stdout_log=value.stdout_log,
        stderr_log=value.stderr_log,
        gui_endpoint=value.control_endpoint,
    )
