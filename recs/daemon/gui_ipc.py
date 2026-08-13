import os
import threading
import time
from collections.abc import Callable, Iterable, Iterator, Mapping
from pathlib import Path

from pydantic import BaseModel, ValidationError
from reccy import ipc, logging, settings
from threa import Runnable

from recs.base.errors import ErrorRecord, RecsError
from recs.cfg.cfg import Cfg
from recs.ui.key_events import KeyEvent

from . import gui_backend, gui_protocol, paths
from .models import DaemonMetadata, DaemonStatus

LOGGER = logging.get_logger(__name__)
STATUS_UPDATE_PERIOD = 1.0


class ControlRequest:
    def __init__(self, request: gui_protocol.Request) -> None:
        self.request = request
        self.response: gui_protocol.Response | None = None
        self.ready = threading.Event()

    def respond(self, response: gui_protocol.Response) -> None:
        self.response = response
        self.ready.set()

    def wait_for_response(self) -> gui_protocol.Response:
        self.ready.wait()
        assert self.response is not None
        return self.response


class DaemonGuiServer(Runnable):
    def __init__(
        self,
        rows: Callable[[], Iterator[Mapping[str, object]]],
        cfg: Cfg,
        *,
        errors: Callable[[], Iterable[ErrorRecord]] | None = None,
        external_rows: Callable[[list[dict[str, object]], list[ErrorRecord]], None]
        | None = None,
    ) -> None:
        self.rows = rows
        self.errors = errors or tuple
        self.external_rows = external_rows
        self.external_ipc_error: str | None = None
        self.cfg = cfg
        self.enabled = daemon_mode_enabled()
        self.paths = paths.service_paths(paths.current_platform())
        self.endpoint = self.paths.gui_endpoint
        self.backend = gui_backend.server_backend(self.endpoint)
        self.clients: list[GuiListener] = []
        self.key_events: list[KeyEvent] = []
        self.control_requests: list[ControlRequest] = []
        self.shutdown_started = False
        self.last_status_update: float | None = None
        self.lock = threading.Lock()
        super().__init__()

    def start(self) -> None:
        if not self.enabled:
            super().start()
            return

        try:
            self.backend.start()
        except OSError as e:
            _write_status(
                self.paths.status,
                self._status(gui_ipc_error=str(e)),
            )
            LOGGER.warning('Cannot start GUI IPC server: %s', e)
            super().start()
            return

        _write_status(self.paths.status, self._status())
        self.last_status_update = time.monotonic()
        super().start()
        threading.Thread(
            target=self._accept,
            daemon=True,
            name='DaemonGuiAccept',
        ).start()

    def update(self) -> None:
        if not self.enabled:
            return
        rows = [dict(row) for row in self.rows()]
        errors = list(self.errors())
        now = time.monotonic()
        if (
            self.last_status_update is None
            or now - self.last_status_update >= STATUS_UPDATE_PERIOD
        ):
            _write_status(self.paths.status, self._status(rows=rows, errors=errors))
            self.last_status_update = now
        self.broadcast(rows, errors)
        if self.external_rows is not None:
            self.external_rows(rows, errors)

    @property
    def closed(self) -> bool:
        return self.shutdown_started

    def take_key_events(self) -> list[KeyEvent]:
        with self.lock:
            events, self.key_events = self.key_events, []
        return events

    def take_control_requests(self) -> list[ControlRequest]:
        with self.lock:
            requests, self.control_requests = self.control_requests, []
        return requests

    def broadcast(
        self, rows: list[dict[str, object]], errors: list[ErrorRecord]
    ) -> None:
        message = ipc.message_json(
            gui_protocol.RowsMessage(type='rows', rows=rows, errors=errors)
        )
        with self.lock:
            listeners = list(self.clients)
        for listener in listeners:
            if not listener.write(message):
                self._remove(listener)

    def stop(self) -> None:
        self.request_shutdown()

    def request_shutdown(self) -> None:
        with self.lock:
            if self.shutdown_started:
                return
            self.shutdown_started = True
            listeners = list(self.clients)

        message = ipc.message_json(gui_protocol.Shutdown(type='shutdown'))
        for listener in listeners:
            listener.write(message)
            listener.close()
        self.backend.close()
        super().stop()

    def _accept(self) -> None:
        while self.running:
            if (conn := self.backend.accept()) is None:
                continue

            listener = GuiListener(
                conn,
                self._append_key_event,
                self._append_control_request,
                self.request_shutdown,
            )
            with self.lock:
                self.clients.append(listener)
            listener.start()

    def _append_key_event(self, event: KeyEvent) -> None:
        with self.lock:
            self.key_events.append(event)

    def _append_control_request(self, request: ControlRequest) -> None:
        with self.lock:
            self.control_requests.append(request)

    def _remove(self, listener: 'GuiListener') -> None:
        listener.close()
        with self.lock:
            if listener in self.clients:
                self.clients.remove(listener)

    def _status(
        self,
        *,
        gui_ipc_error: str | None = None,
        rows: list[dict[str, object]] | None = None,
        errors: list[ErrorRecord] | None = None,
    ) -> DaemonStatus:
        with self.lock:
            client_count = len(self.clients)
        return DaemonStatus(
            client_count=client_count,
            errors=errors or [],
            external_ipc_error=self.external_ipc_error,
            gui_ipc_error=gui_ipc_error,
            recording=True,
            rows=rows or [],
            updated_at=time.time(),
        )


class GuiListener:
    def __init__(
        self,
        conn: ipc.Connection,
        append_key_event: Callable[[KeyEvent], None],
        append_control_request: Callable[[ControlRequest], None] | None = None,
        request_shutdown: Callable[[], None] | None = None,
    ) -> None:
        self.append_key_event = append_key_event
        self.append_control_request = append_control_request
        self.protocol = ipc.ProtocolListener(
            conn,
            parse=gui_protocol.parse_message,
            version=gui_protocol.VERSION,
            peer_role='GUI',
            local_role='daemon',
            on_message=self._handle_message,
            request_shutdown=request_shutdown,
            logger=LOGGER,
        )

    def start(self) -> None:
        threading.Thread(target=self._read, daemon=True, name='DaemonGuiClient').start()

    def write(self, message: str) -> bool:
        return self.protocol.write(message)

    def write_model(self, message: BaseModel, *, exclude_none: bool = False) -> bool:
        return self.protocol.write_model(message, exclude_none=exclude_none)

    def close(self) -> None:
        self.protocol.close()

    def _read(self) -> None:
        self.protocol.read()

    def _handle_message(
        self,
        listener: ipc.ProtocolListener,
        message: object,
    ) -> None:
        if isinstance(message, (gui_protocol.KeyPressed, gui_protocol.KeyReleased)):
            self.append_key_event(KeyEvent(type=message.type, key=message.key))
        elif isinstance(message, gui_protocol.Request) and self.append_control_request:
            request = ControlRequest(message)
            self.append_control_request(request)
            self.write_model(request.wait_for_response(), exclude_none=True)


class RemoteGuiClient:
    def __init__(self, endpoint: str | Path) -> None:
        self.endpoint = endpoint
        self.connection: ipc.Connection | None = None
        self.latest: list[dict[str, object]] = []
        self.latest_errors: list[ErrorRecord] = []
        self.closed = False
        self.lock = threading.Lock()

    def start(self) -> None:
        self.connection = gui_backend.client_connection(self.endpoint)
        if not self._write(
            ipc.message_json(
                gui_protocol.Hello(
                    type='hello',
                    role='gui',
                    version=gui_protocol.VERSION,
                )
            )
        ):
            self.closed = True
            raise BrokenPipeError('Could not send GUI hello')
        threading.Thread(target=self._read, daemon=True, name='RemoteGuiRows').start()

    def rows(self) -> Iterator[Mapping[str, object]]:
        with self.lock:
            rows = list(self.latest)
        return iter(rows)

    def errors(self) -> list[str]:
        with self.lock:
            return [error.message for error in self.latest_errors]

    def record_key(self, event: KeyEvent) -> None:
        self._write(ipc.message_json(event))

    def shutdown(self) -> None:
        self._write(ipc.message_json(gui_protocol.Shutdown(type='shutdown')))

    def _write(self, message: str) -> bool:
        if self.connection is None:
            return False
        return self.connection.write(message)

    def _read(self) -> None:
        if self.connection is None:
            return
        for line in self.connection.read_lines():
            try:
                message = gui_protocol.parse_message(line)
            except ValidationError:
                continue
            if isinstance(message, gui_protocol.Error):
                LOGGER.error('%s', message.message)
                self.closed = True
                return
            if (
                isinstance(message, gui_protocol.Hello)
                and message.version != gui_protocol.VERSION
            ):
                LOGGER.error(
                    'Daemon GUI protocol version %s is not supported; '
                    'client requires %s',
                    message.version,
                    gui_protocol.VERSION,
                )
                self.closed = True
                return
            if isinstance(message, gui_protocol.RowsMessage):
                with self.lock:
                    self.latest = message.rows
                    self.latest_errors = message.errors
            if isinstance(message, gui_protocol.Shutdown):
                self.closed = True
                return
        self.closed = True


def endpoint_reachable(metadata: DaemonMetadata) -> bool:
    try:
        connection = gui_backend.client_connection(_endpoint(metadata.gui_endpoint))
    except (OSError, ValueError):
        return False
    connection.close()
    return True


def load_metadata() -> DaemonMetadata | None:
    path = paths.service_paths(paths.current_platform()).metadata
    if not path.exists():
        return None
    try:
        return DaemonMetadata.model_validate_json(path.read_text())
    except ValidationError:
        return None


def run_remote_gui(metadata: DaemonMetadata, cfg: Cfg) -> None:
    from recs.ui.pyside_gui import Gui

    client = RemoteGuiClient(_endpoint(metadata.gui_endpoint))
    try:
        client.start()
    except (OSError, ValueError) as e:
        raise RecsError(f'Could not connect to daemon GUI: {e}') from None
    Gui(
        client.rows,
        cfg,
        errors=client.errors,
        stop_when=lambda: client.closed,
        record_key=client.record_key,
    ).run()


def _endpoint(endpoint: str) -> Path | str:
    if endpoint == gui_backend.WINDOWS_PIPE:
        return endpoint
    return Path(endpoint)


def daemon_mode_enabled() -> bool:
    return os.environ.get('RECS_DAEMON') == '1'


def _write_status(path: Path, status: DaemonStatus) -> None:
    settings.write_json_model(path, status, sync=False)
