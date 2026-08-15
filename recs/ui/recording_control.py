from collections.abc import Callable
from typing import Protocol

from pydantic import ValidationError

from recs.base.errors import ErrorRecord, RecsError
from recs.daemon import external_ipc, gui_ipc, gui_protocol


class ControlDisplay(Protocol):
    def take_control_requests(self) -> list[gui_ipc.ControlRequest]:
        ...


class RecordingControl:
    def __init__(self) -> None:
        self.shutdown_started = False

    def receive(
        self,
        live: ControlDisplay | None,
        external: external_ipc.ExternalServer | None,
        handle: Callable[[gui_protocol.Request], gui_protocol.Response],
        warning: Callable[[str], None],
        shutdown: Callable[[], None],
    ) -> None:
        if isinstance(live, gui_ipc.DaemonGuiServer):
            for error in live.take_protocol_errors():
                warning(f'Malformed GUI protocol message: {error}')
        requests = live.take_control_requests() if live is not None else []
        for request in requests:
            try:
                response = handle(request.request)
            except RecsError as error:
                response = gui_protocol.Error(type='error', message=str(error))
            request.respond(response)
        if external is None:
            return
        for request in external.take_requests():
            try:
                parsed = external_ipc.recs_request(request.request)
                if isinstance(parsed, gui_protocol.Shutdown):
                    if not self.shutdown_started:
                        self.shutdown_started = True
                        shutdown()
                    response = gui_protocol.RecordingState(
                        type='recording_state', paused=False, stopped=True
                    )
                else:
                    response = handle(parsed)
            except (RecsError, ValidationError) as error:
                warning(f'External Recs protocol error: {error}')
                response = gui_protocol.Error(type='error', message=str(error))
            external.respond(request, external_ipc.response(request.request, response))

    def publish(
        self,
        external: external_ipc.ExternalServer | None,
        rows: list[dict[str, object]],
        errors: list[ErrorRecord],
    ) -> None:
        if external is not None:
            external.publish_rows(rows, errors)
