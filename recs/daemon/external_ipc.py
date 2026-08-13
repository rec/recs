from __future__ import annotations

import threading
from pathlib import Path

from reccy import rpc

from recs.base.errors import ErrorRecord, RecsError

from . import gui_protocol


class ControlRequest:
    def __init__(self, request: rpc.Request) -> None:
        self.request = request
        self.response: rpc.Response | None = None
        self.ready = threading.Event()

    def respond(self, response: rpc.Response) -> None:
        self.response = response
        self.ready.set()

    def wait(self) -> rpc.Response:
        self.ready.wait()
        assert self.response is not None
        return self.response


class ExternalServer:
    def __init__(
        self, control_endpoint: Path | str, event_endpoint: Path | str
    ) -> None:
        self.requests: list[ControlRequest] = []
        self.pending: list[ControlRequest] = []
        self.lock = threading.Lock()
        self.closed = False
        self.shutdown_published = False
        self.server = rpc.Server(
            control_endpoint,
            event_endpoint,
            self._handle,
            role='recs',
        )

    def start(self) -> None:
        self.server.start()

    def close(self) -> None:
        self.publish_shutdown()
        with self.lock:
            if self.closed:
                return
            self.closed = True
            requests, self.requests = self.pending, []
            self.pending = []
        for request in requests:
            request.respond(
                rpc.Response(
                    id=request.request.id,
                    ok=False,
                    message='recs is shutting down',
                )
            )
        self.server.close()

    def take_requests(self) -> list[ControlRequest]:
        with self.lock:
            requests, self.requests = self.requests, []
        return requests

    def respond(self, request: ControlRequest, response: rpc.Response) -> None:
        with self.lock:
            if request in self.pending:
                self.pending.remove(request)
        request.respond(response)

    def publish_rows(
        self,
        rows: list[dict[str, object]],
        errors: list[ErrorRecord],
    ) -> None:
        self.server.publish('rows', rows=rows, errors=errors)

    def publish_shutdown(self) -> None:
        with self.lock:
            if self.shutdown_published:
                return
            self.shutdown_published = True
        self.server.publish('shutdown')

    def _handle(self, request: rpc.Request) -> rpc.Response:
        control = ControlRequest(request)
        with self.lock:
            if self.closed:
                return rpc.Response(
                    id=request.id,
                    ok=False,
                    message='recs is shutting down',
                )
            self.requests.append(control)
            self.pending.append(control)
        return control.wait()


def recs_request(request: rpc.Request) -> gui_protocol.Request | gui_protocol.Shutdown:
    message = gui_protocol.MESSAGE.validate_python(
        request.params | {'type': request.command}
    )
    if isinstance(message, gui_protocol.Request | gui_protocol.Shutdown):
        return message
    raise RecsError(f'Unsupported request: {request.command}')


def response(request: rpc.Request, value: gui_protocol.Response) -> rpc.Response:
    if isinstance(value, gui_protocol.Error):
        return rpc.Response(id=request.id, ok=False, message=value.message)
    return rpc.Response(id=request.id, ok=True, result=value.model_dump())
