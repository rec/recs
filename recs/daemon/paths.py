from pathlib import Path

from reccy import models, paths

from .models import ServicePaths
from .spec import RECS_SERVICE


def current_platform() -> models.Platform:
    return paths.current_platform()


def service_paths(
    platform: models.Platform,
    home: Path | None = None,
    service: models.ServiceSpec = RECS_SERVICE,
) -> ServicePaths:
    value = paths.service_paths(service, platform, home)
    return ServicePaths(
        metadata=value.metadata,
        service=value.service,
        status=value.status,
        stdout_log=value.stdout_log,
        stderr_log=value.stderr_log,
        gui_endpoint=value.control_endpoint,
    )
