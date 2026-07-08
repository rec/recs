import logging
import sys
import threading
import typing as t
from pathlib import Path

from pydantic import ValidationError
from threa import Runnable

from recs.cfg import Cfg
from recs.ui.key_events import KeyEvent

from . import paths
from .gui_backend import (
    WINDOWS_PIPE,
    GuiConnection,
    client_connection,
    server_backend,
)
from .gui_protocol import (
    VERSION,
    Error,
    Hello,
    KeyPressed,
    KeyReleased,
    RowsMessage,
    parse_message,
)
from .models import DaemonMetadata

LOGGER = logging.getLogger(__name__)


class DaemonGuiServer(Runnable):
    def __init__(
        self, rows: t.Callable[[], t.Iterator[t.Mapping[str, object]]], cfg: Cfg
    ) -> None:
        self.rows = rows
        self.cfg = cfg
        self.enabled = daemon_mode_enabled()
        self.endpoint = paths.service_paths(paths.current_platform()).gui_endpoint
        self.backend = server_backend(self.endpoint)
        self.clients: list[GuiListener] = []
        self.key_events: list[KeyEvent] = []
        self.lock = threading.Lock()
        super().__init__()

    def start(self) -> None:
        if not self.enabled:
            super().start()
            return

        try:
            self.backend.start()
        except OSError as e:
            LOGGER.warning('Cannot start GUI IPC server: %s', e)
            super().start()
            return

        super().start()
        threading.Thread(
            target=self._accept,
            daemon=True,
            name='DaemonGuiAccept',
        ).start()

    def update(self) -> None:
        if not self.enabled:
            return
        self.broadcast([dict(row) for row in self.rows()])

    @property
    def closed(self) -> bool:
        return False

    def take_key_events(self) -> list[KeyEvent]:
        with self.lock:
            events, self.key_events = self.key_events, []
        return events

    def broadcast(self, rows: list[dict[str, object]]) -> None:
        message = RowsMessage(type='rows', rows=rows).model_dump_json() + '\n'
        with self.lock:
            listeners = list(self.clients)
        for listener in listeners:
            if not listener.write(message):
                self._remove(listener)

    def stop(self) -> None:
        self.backend.close()
        for listener in self.clients:
            listener.close()
        super().stop()

    def _accept(self) -> None:
        while self.running:
            if (conn := self.backend.accept()) is None:
                continue

            listener = GuiListener(conn, self._append_key_event)
            with self.lock:
                self.clients.append(listener)
            listener.start()

    def _append_key_event(self, event: KeyEvent) -> None:
        with self.lock:
            self.key_events.append(event)

    def _remove(self, listener: 'GuiListener') -> None:
        listener.close()
        with self.lock:
            if listener in self.clients:
                self.clients.remove(listener)


class GuiListener:
    def __init__(
        self, conn: GuiConnection, append_key_event: t.Callable[[KeyEvent], None]
    ) -> None:
        self.conn = conn
        self.append_key_event = append_key_event
        self.lock = threading.Lock()

    def start(self) -> None:
        threading.Thread(target=self._read, daemon=True, name='DaemonGuiClient').start()

    def write(self, message: str) -> bool:
        with self.lock:
            return self.conn.write(message)

    def close(self) -> None:
        self.conn.close()

    def _read(self) -> None:
        for line in self.conn.read_lines():
            try:
                message = parse_message(line)
            except ValidationError:
                LOGGER.warning('Ignoring malformed GUI message')
                continue
            if isinstance(message, Hello):
                self._receive_hello(message)
                continue
            if isinstance(message, (KeyPressed, KeyReleased)):
                self.append_key_event(KeyEvent(type=message.type, key=message.key))

    def _receive_hello(self, message: Hello) -> None:
        if message.version != VERSION:
            self.write(
                Error(
                    type='error',
                    message=(
                        f'GUI protocol version {message.version} is not supported; '
                        f'daemon requires {VERSION}'
                    ),
                ).model_dump_json()
                + '\n'
            )
            self.close()
            return
        self.write(
            Hello(type='hello', role='daemon', version=VERSION).model_dump_json() + '\n'
        )


class RemoteGuiClient:
    def __init__(self, endpoint: str | Path) -> None:
        self.endpoint = endpoint
        self.connection: GuiConnection | None = None
        self.latest: list[dict[str, object]] = []
        self.closed = False
        self.lock = threading.Lock()

    def start(self) -> None:
        self.connection = client_connection(self.endpoint)
        self._write(
            Hello(type='hello', role='gui', version=VERSION).model_dump_json() + '\n'
        )
        threading.Thread(target=self._read, daemon=True, name='RemoteGuiRows').start()

    def rows(self) -> t.Iterator[t.Mapping[str, object]]:
        with self.lock:
            rows = list(self.latest)
        return iter(rows)

    def record_key(self, event: KeyEvent) -> None:
        self._write(event.model_dump_json() + '\n')

    def _write(self, message: str) -> None:
        if self.connection is None:
            return
        self.connection.write(message)

    def _read(self) -> None:
        if self.connection is None:
            return
        for line in self.connection.read_lines():
            try:
                message = parse_message(line)
            except ValidationError:
                continue
            if isinstance(message, Error):
                print(message.message, file=sys.stderr)
                self.closed = True
                return
            if isinstance(message, Hello) and message.version != VERSION:
                print(
                    f'Daemon GUI protocol version {message.version} is not supported; '
                    f'client requires {VERSION}',
                    file=sys.stderr,
                )
                self.closed = True
                return
            if isinstance(message, RowsMessage):
                with self.lock:
                    self.latest = message.rows
        self.closed = True


def endpoint_reachable(metadata: DaemonMetadata) -> bool:
    try:
        connection = client_connection(_endpoint(metadata.gui_endpoint))
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
    client.start()
    Gui(
        client.rows,
        cfg,
        stop_when=lambda: client.closed,
        record_key=client.record_key,
    ).run()


def _endpoint(endpoint: str) -> Path | str:
    if endpoint == WINDOWS_PIPE:
        return endpoint
    return Path(endpoint)


def daemon_mode_enabled() -> bool:
    import os

    return os.environ.get('RECS_DAEMON') == '1'
