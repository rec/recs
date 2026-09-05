from pathlib import Path

from reccy.services import models, paths

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
        log=value.log,
        gui_endpoint=value.control_endpoint,
    )


def external_control_endpoint(
    home: Path | None = None,
    platform: models.Platform | None = None,
) -> Path | str:
    if (platform or current_platform()) == models.Platform.windows:
        return r'\\.\pipe\recs-control'
    return (home or Path.home()) / '.local/state/recs/control.sock'


def external_event_endpoint(
    home: Path | None = None,
    platform: models.Platform | None = None,
) -> Path | str:
    if (platform or current_platform()) == models.Platform.windows:
        return r'\\.\pipe\recs-events'
    return (home or Path.home()) / '.local/state/recs/events.sock'
