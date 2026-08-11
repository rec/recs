import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import cast

from reccy import models, service

from . import paths
from .models import DaemonMetadata, DaemonStatus, StatusResult
from .spec import RECS_SERVICE


class ServiceController:
    def __init__(
        self,
        platform: models.Platform,
        home: Path | None = None,
        runner: Callable[..., subprocess.CompletedProcess[str]] | None = None,
        service_definition: models.ServiceSpec = RECS_SERVICE,
    ) -> None:
        self.platform = platform
        self.service = service_definition
        self.paths = paths.service_paths(platform, home, service_definition)
        self._controller = service.ServiceController(
            service_definition,
            platform,
            home,
            runner,
            status_model=DaemonStatus,
            status_error_attribute='gui_ipc_error',
            status_error_label='GUI IPC error',
        )

    def install(self, metadata: DaemonMetadata) -> StatusResult:
        return _status_result(
            self._controller.install(cast(models.DaemonMetadata, metadata))
        )

    def uninstall(self) -> StatusResult:
        return _status_result(self._controller.uninstall())

    def start(self) -> StatusResult:
        return _status_result(self._controller.start())

    def stop(self) -> StatusResult:
        return _status_result(self._controller.stop())

    def restart(self) -> StatusResult:
        return _status_result(self._controller.restart())

    def status(self) -> StatusResult:
        return _status_result(self._controller.status())


def _status_result(value: models.StatusResult) -> StatusResult:
    return StatusResult(
        health=cast(DaemonStatus | None, value.health),
        installed=value.installed,
        running=value.running,
        details=value.details,
    )
