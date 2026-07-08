import time
from pathlib import Path

import pytest

from recs.daemon import gui_backend


def test_backend_selects_unix_socket_for_path() -> None:
    backend = gui_backend.server_backend(Path('/tmp/recs.sock'))

    assert isinstance(backend, gui_backend.UnixSocketServerBackend)


def test_backend_selects_windows_pipe_for_string() -> None:
    backend = gui_backend.server_backend(gui_backend.WINDOWS_PIPE)

    assert isinstance(backend, gui_backend.WindowsPipeServerBackend)


def test_windows_pipe_server_accepts_connections(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    listener = FakeListener(gui_backend.WINDOWS_PIPE, family='AF_PIPE')
    monkeypatch.setattr(
        gui_backend.mp_connection,
        'Listener',
        lambda endpoint, family: listener,
    )
    backend = gui_backend.WindowsPipeServerBackend(gui_backend.WINDOWS_PIPE)

    backend.start()
    connection = backend.accept()
    backend.close()

    assert connection is not None
    assert listener.endpoint == gui_backend.WINDOWS_PIPE
    assert listener.family == 'AF_PIPE'
    assert listener.closed


def test_windows_pipe_client_uses_named_pipe_family(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pipe = FakePipe()
    calls: list[tuple[str, str]] = []

    def connect(endpoint: str, family: str) -> FakePipe:
        calls.append((endpoint, family))
        return pipe

    monkeypatch.setattr(gui_backend.mp_connection, 'Client', connect)
    connection = gui_backend.WindowsPipeConnection.connect(gui_backend.WINDOWS_PIPE)

    connection.write('hello\n')

    assert calls == [(gui_backend.WINDOWS_PIPE, 'AF_PIPE')]
    assert pipe.sent == ['hello\n']


def test_windows_pipe_client_times_out(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def connect(endpoint: str, family: str) -> FakePipe:
        time.sleep(0.1)
        return FakePipe()

    monkeypatch.setattr(gui_backend, 'PIPE_CONNECT_TIMEOUT', 0.01)
    monkeypatch.setattr(gui_backend.mp_connection, 'Client', connect)

    with pytest.raises(TimeoutError, match='Timed out connecting'):
        gui_backend.WindowsPipeConnection.connect(gui_backend.WINDOWS_PIPE)


def test_windows_pipe_connection_reads_until_closed() -> None:
    pipe = FakePipe(['first\n', 'second\n'])
    connection = gui_backend.WindowsPipeConnection(pipe)

    assert list(connection.read_lines()) == ['first\n', 'second\n']


class FakeListener:
    def __init__(self, endpoint: str, *, family: str) -> None:
        self.endpoint = endpoint
        self.family = family
        self.closed = False
        self.pipe = FakePipe()

    def accept(self) -> 'FakePipe':
        return self.pipe

    def close(self) -> None:
        self.closed = True


class FakePipe:
    def __init__(self, received: list[str] | None = None) -> None:
        self.received = received or []
        self.sent: list[str] = []
        self.closed = False

    def recv(self) -> str:
        if not self.received:
            raise EOFError
        return self.received.pop(0)

    def send(self, message: str) -> None:
        self.sent.append(message)

    def close(self) -> None:
        self.closed = True
