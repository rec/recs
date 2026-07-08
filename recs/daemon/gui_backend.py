import multiprocessing.connection as mp_connection
import socket
import typing as t
from pathlib import Path

SOCKET_TIMEOUT = 0.2
WINDOWS_PIPE = r'\\.\pipe\recs'


class GuiConnection(t.Protocol):
    def read_lines(self) -> t.Iterator[str]:
        ...

    def write(self, message: str) -> bool:
        ...

    def close(self) -> None:
        ...


class GuiServerBackend(t.Protocol):
    def start(self) -> None:
        ...

    def accept(self) -> GuiConnection | None:
        ...

    def close(self) -> None:
        ...


def server_backend(endpoint: str | Path) -> GuiServerBackend:
    if isinstance(endpoint, Path):
        return UnixSocketServerBackend(endpoint)
    return WindowsPipeServerBackend(endpoint)


def client_connection(endpoint: str | Path) -> GuiConnection:
    if isinstance(endpoint, Path):
        return UnixSocketConnection.connect(endpoint)
    return WindowsPipeConnection.connect(endpoint)


class UnixSocketServerBackend:
    def __init__(self, endpoint: Path) -> None:
        self.endpoint = endpoint
        self.socket: socket.socket | None = None

    def start(self) -> None:
        self.endpoint.parent.mkdir(parents=True, exist_ok=True)
        _remove_stale_socket(self.endpoint)
        self.socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.socket.bind(str(self.endpoint))
        self.socket.listen()
        self.socket.settimeout(SOCKET_TIMEOUT)

    def accept(self) -> GuiConnection | None:
        if self.socket is None:
            return None
        try:
            conn, _ = self.socket.accept()
        except TimeoutError:
            return None
        except OSError:
            return None
        return UnixSocketConnection(conn)

    def close(self) -> None:
        if self.socket is not None:
            self.socket.close()


class UnixSocketConnection:
    def __init__(self, conn: socket.socket) -> None:
        self.conn = conn
        self.file = conn.makefile('r', encoding='utf-8')

    @classmethod
    def connect(cls, endpoint: Path) -> 'UnixSocketConnection':
        conn = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        conn.settimeout(SOCKET_TIMEOUT)
        conn.connect(str(endpoint))
        conn.settimeout(None)
        return cls(conn)

    def read_lines(self) -> t.Iterator[str]:
        yield from self.file

    def write(self, message: str) -> bool:
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


class WindowsPipeServerBackend:
    def __init__(self, endpoint: str) -> None:
        self.endpoint = endpoint
        self.listener: mp_connection.Listener | None = None

    def start(self) -> None:
        self.listener = mp_connection.Listener(self.endpoint, family='AF_PIPE')

    def accept(self) -> GuiConnection | None:
        if self.listener is None:
            return None
        try:
            return WindowsPipeConnection(self.listener.accept())
        except OSError:
            return None

    def close(self) -> None:
        if self.listener is not None:
            self.listener.close()


class WindowsPipeConnection:
    def __init__(self, conn: mp_connection.Connection) -> None:
        self.conn = conn

    @classmethod
    def connect(cls, endpoint: str) -> 'WindowsPipeConnection':
        return cls(mp_connection.Client(endpoint, family='AF_PIPE'))

    def read_lines(self) -> t.Iterator[str]:
        while True:
            try:
                yield str(self.conn.recv())
            except (EOFError, OSError):
                return

    def write(self, message: str) -> bool:
        try:
            self.conn.send(message)
        except (BrokenPipeError, EOFError, OSError):
            return False
        return True

    def close(self) -> None:
        try:
            self.conn.close()
        except OSError:
            pass


def _remove_stale_socket(path: Path) -> None:
    if not path.exists():
        return
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as conn:
            conn.settimeout(SOCKET_TIMEOUT)
            conn.connect(str(path))
    except OSError:
        path.unlink()
