from __future__ import annotations

import threading
from pathlib import Path
from typing import ClassVar

from pydantic import PrivateAttr
from reccy import ipc, models, rpc
from reccy.reccy import Reccy

from recs.base.errors import ErrorRecord, RecsError

from . import gui_protocol, paths
from .spec import RECS_SERVICE


class ControlRequest:
    def __init__(self, request: rpc.Request) -> None:
        self.request = request
        self.response: rpc.Result | None = None
        self.ready = threading.Event()

    def respond(self, response: rpc.Result) -> None:
        self.response = response
        self.ready.set()

    def wait(self) -> rpc.Result:
        self.ready.wait()
        assert self.response is not None
        return self.response


class ExternalServer(Reccy):
    service_spec: ClassVar[models.ServiceSpec] = RECS_SERVICE
    rpc_enabled = True
    rpc_role = 'recs'
    logger_name = __name__

    _requests: list[ControlRequest] = PrivateAttr(default_factory=list)
    _pending: list[ControlRequest] = PrivateAttr(default_factory=list)
    _lock: threading.Lock = PrivateAttr(default_factory=threading.Lock)
    _shutdown_events: list[None] = PrivateAttr(default_factory=list)

    @property
    def control_endpoint(self) -> Path | str:
        return paths.external_control_endpoint(self.home, self.platform)

    @property
    def event_endpoint(self) -> Path | str:
        return paths.external_event_endpoint(self.home, self.platform)

    def start(self) -> None:
        try:
            super().start()
        except OSError:
            if self._rpc_server is not None:
                self._rpc_server.close()
                object.__setattr__(self, '_rpc_server', None)
            raise

    def take_requests(self) -> list[ControlRequest]:
        with self._lock:
            requests = self._requests.copy()
            self._requests.clear()
        return requests

    def respond(self, request: ControlRequest, response: rpc.Result) -> None:
        with self._lock:
            if request in self._pending:
                self._pending.remove(request)
        request.respond(response)

    def publish_rows(
        self,
        rows: list[dict[str, object]],
        errors: list[ErrorRecord],
    ) -> None:
        self.publish_event('rows', rows=rows, errors=errors)

    def rpc_response(self, request: rpc.Request) -> rpc.Result:
        control = ControlRequest(request)
        with self._lock:
            if not self._started:
                return ipc.Error(type='error', message='recs is shutting down')
            if self._pending:
                return ipc.Error(
                    type='error',
                    message='recs already has an active control client',
                )
            self._requests.append(control)
            self._pending.append(control)
        return control.wait()

    def on_stopping(self) -> None:
        self._publish_shutdown()
        with self._lock:
            requests = self._pending.copy()
            self._requests.clear()
            self._pending.clear()
        for request in requests:
            request.respond(ipc.Error(type='error', message='recs is shutting down'))

    def _publish_shutdown(self) -> None:
        with self._lock:
            if self._shutdown_events:
                return
            self._shutdown_events.append(None)
        self.publish_event('shutdown')


def recs_request(request: rpc.Request) -> gui_protocol.Request | gui_protocol.Shutdown:
    message = gui_protocol.MESSAGE.validate_python(
        request.params | {'type': request.command}
    )
    if isinstance(message, gui_protocol.Request | gui_protocol.Shutdown):
        return message
    raise RecsError(f'Unsupported request: {request.command}')


def response(request: rpc.Request, value: gui_protocol.Response) -> rpc.Result:
    if isinstance(value, gui_protocol.Error):
        return ipc.Error(type='error', message=value.message)
    if request.command in {
        'calibrate',
        'capabilities',
        'disk_status',
        'get_cfg',
        'get_track_names',
        'list_devices',
        'mutable_attributes',
        'status_snapshot',
    }:
        return value.model_dump()
    return 'ok'
