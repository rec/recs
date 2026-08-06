import subprocess as sp
import typing as t
from pathlib import Path

from reccy import service as reccy_service
from reccy.models import DaemonMetadata as ReccyDaemonMetadata
from reccy.models import StatusResult as ReccyStatusResult
from reccy.service import ServiceController as ReccyServiceController

from . import paths, renderers
from .models import DaemonMetadata, DaemonStatus, Platform, ServiceSpec, StatusResult
from .spec import RECS_SERVICE

__all__ = ['ServiceController', 'reccy_service', 'renderers']


class ServiceController:
    def __init__(
        self,
        platform: Platform,
        home: Path | None = None,
        runner: t.Callable[..., sp.CompletedProcess[str]] | None = None,
        service: ServiceSpec = RECS_SERVICE,
    ) -> None:
        self.platform = platform
        self.service = service
        self.paths = paths.service_paths(platform, home, service)
        self._controller = ReccyServiceController(
            service,
            platform,
            home,
            runner,
            status_model=DaemonStatus,
            status_error_attribute='gui_ipc_error',
            status_error_label='GUI IPC error',
        )

    def install(self, metadata: DaemonMetadata) -> StatusResult:
        return _status_result(
            self._controller.install(t.cast(ReccyDaemonMetadata, metadata))
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


def _status_result(value: ReccyStatusResult) -> StatusResult:
    return StatusResult(
        health=t.cast(DaemonStatus | None, value.health),
        installed=value.installed,
        running=value.running,
        details=value.details,
    )
