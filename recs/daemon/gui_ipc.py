import logging
import socket
import threading
import typing as t
from pathlib import Path

from pydantic import ValidationError
from threa import Runnable

from recs.cfg import Cfg
from recs.ui.key_events import KeyEvent

from . import paths
from .gui_protocol import (
    Hello,
    KeyPressed,
    KeyReleased,
    RowsMessage,
    parse_message,
)
from .models import DaemonMetadata

LOGGER = logging.getLogger(__name__)
SOCKET_TIMEOUT = 0.2
WINDOWS_PIPE = r'\\.\pipe\recs'


class DaemonGuiServer(Runnable):
    def __init__(
        self, rows: t.Callable[[], t.Iterator[t.Mapping[str, object]]], cfg: Cfg
    ) -> None:
        self.rows = rows
        self.cfg = cfg
        self.enabled = daemon_mode_enabled()
        self.endpoint = paths.service_paths(paths.current_platform()).gui_endpoint
        self.socket: socket.socket | None = None
        self.clients: list[GuiListener] = []
        self.key_events: list[KeyEvent] = []
        self.lock = threading.Lock()
        super().__init__()

    def start(self) -> None:
        if not self.enabled:
            super().start()
            return
        if not isinstance(self.endpoint, Path):
            LOGGER.warning('GUI IPC is not supported on this platform')
            super().start()
            return

        self.endpoint.parent.mkdir(parents=True, exist_ok=True)
        _remove_stale_socket(self.endpoint)
        try:
            self.socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            self.socket.bind(str(self.endpoint))
            self.socket.listen()
            self.socket.settimeout(SOCKET_TIMEOUT)
        except OSError as e:
            LOGGER.warning('Cannot start GUI IPC server: %s', e)
            self.socket = None
            super().start()
            return

        super().start()
        threading.Thread(
            target=self._accept,
            daemon=True,
            name='DaemonGuiAccept',
        ).start()

    def update(self) -> None:
        if not self.enabled or self.socket is None:
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
        if self.socket is not None:
            self.socket.close()
        for listener in self.clients:
            listener.close()
        super().stop()

    def _accept(self) -> None:
        while self.running and self.socket is not None:
            try:
                conn, _ = self.socket.accept()
            except TimeoutError:
                continue
            except OSError:
                return

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
        self, conn: socket.socket, append_key_event: t.Callable[[KeyEvent], None]
    ) -> None:
        self.conn = conn
        self.append_key_event = append_key_event
        self.file = conn.makefile('r', encoding='utf-8')
        self.lock = threading.Lock()

    def start(self) -> None:
        threading.Thread(target=self._read, daemon=True, name='DaemonGuiClient').start()

    def write(self, message: str) -> bool:
        with self.lock:
            try:
                self.conn.sendall(message.encode())
            except OSError:
                return False
        return True

    def close(self) -> None:
        try:
            self.conn.close()
        except OSError:
            pass

    def _read(self) -> None:
        for line in self.file:
            try:
                message = parse_message(line)
            except ValidationError:
                LOGGER.warning('Ignoring malformed GUI message')
                continue
            if isinstance(message, (KeyPressed, KeyReleased)):
                self.append_key_event(KeyEvent(type=message.type, key=message.key))


class RemoteGuiClient:
    def __init__(self, endpoint: str | Path) -> None:
        self.endpoint = endpoint
        self.socket: socket.socket | None = None
        self.file: t.TextIO | None = None
        self.latest: list[dict[str, object]] = []
        self.closed = False
        self.lock = threading.Lock()

    def start(self) -> None:
        if not isinstance(self.endpoint, Path):
            raise OSError('GUI IPC is not supported on this platform')

        self.socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.socket.connect(str(self.endpoint))
        self.file = self.socket.makefile(encoding='utf-8')
        self._write(Hello(type='hello', role='gui').model_dump_json() + '\n')
        threading.Thread(target=self._read, daemon=True, name='RemoteGuiRows').start()

    def rows(self) -> t.Iterator[t.Mapping[str, object]]:
        with self.lock:
            rows = list(self.latest)
        return iter(rows)

    def record_key(self, event: KeyEvent) -> None:
        self._write(event.model_dump_json() + '\n')

    def _write(self, message: str) -> None:
        if self.socket is None:
            return
        self.socket.sendall(message.encode())

    def _read(self) -> None:
        if self.file is None:
            return
        for line in self.file:
            try:
                message = parse_message(line)
            except ValidationError:
                continue
            if isinstance(message, RowsMessage):
                with self.lock:
                    self.latest = message.rows
        self.closed = True


def endpoint_reachable(metadata: DaemonMetadata) -> bool:
    endpoint = _endpoint(metadata.gui_endpoint)
    if not isinstance(endpoint, Path):
        return False

    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as conn:
            conn.settimeout(SOCKET_TIMEOUT)
            conn.connect(str(endpoint))
    except OSError:
        return False
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


def _remove_stale_socket(path: Path) -> None:
    if not path.exists():
        return
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as conn:
            conn.settimeout(SOCKET_TIMEOUT)
            conn.connect(str(path))
    except OSError:
        path.unlink()
