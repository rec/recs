import socket
import typing as t
import uuid
from pathlib import Path

import pytest
from pydantic import ValidationError

from recs.cfg import Cfg
from recs.daemon import gui_ipc
from recs.daemon.gui_protocol import RowsMessage, parse_message
from recs.daemon.models import DaemonMetadata, Platform
from recs.ui.key_events import KeyEvent


def test_protocol_parses_valid_messages() -> None:
    message = parse_message('{"type":"rows","rows":[{"device":"Mic"}]}')

    assert isinstance(message, RowsMessage)
    assert message.rows == [{'device': 'Mic'}]


def test_protocol_rejects_malformed_messages() -> None:
    with pytest.raises(ValidationError):
        parse_message('{"type":"rows"}')


def test_protocol_rejects_unknown_key_messages() -> None:
    with pytest.raises(ValidationError):
        parse_message('{"type":"unknown","key":"g"}')


def test_daemon_publisher_broadcasts_rows_to_listeners() -> None:
    server = gui_ipc.DaemonGuiServer(lambda: iter([{'device': 'Mic'}]), Cfg())
    first = FakeListener()
    second = FakeListener()
    server.clients = [first, second]

    server.broadcast([{'device': 'Mic'}])

    assert first.messages == ['{"type":"rows","rows":[{"device":"Mic"}]}\n']
    assert second.messages == first.messages


def test_daemon_publisher_removes_broken_listeners() -> None:
    server = gui_ipc.DaemonGuiServer(lambda: iter([{'device': 'Mic'}]), Cfg())
    good = FakeListener()
    broken = FakeListener(broken=True)
    server.clients = [good, broken]

    server.broadcast([{'device': 'Mic'}])

    assert server.clients == [good]
    assert broken.closed


def test_remote_row_provider_exposes_latest_rows() -> None:
    endpoint = _socket_path()
    listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    listener.bind(str(endpoint))
    listener.listen()
    client = gui_ipc.RemoteGuiClient(endpoint)

    client.start()
    conn, _ = listener.accept()
    conn.recv(1024)
    conn.sendall(b'{"type":"rows","rows":[{"device":"Mic"}]}\n')

    assert _eventually(lambda: list(client.rows()) == [{'device': 'Mic'}])


def test_remote_row_provider_sends_key_events() -> None:
    endpoint = _socket_path()
    listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    listener.bind(str(endpoint))
    listener.listen()
    client = gui_ipc.RemoteGuiClient(endpoint)

    client.start()
    conn, _ = listener.accept()
    conn.recv(1024)
    client.record_key(KeyEvent(type='key_pressed', key='g'))

    assert b'"type":"key_pressed"' in conn.recv(1024)


def test_endpoint_reachable_checks_metadata_socket() -> None:
    endpoint = _socket_path()
    listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    listener.bind(str(endpoint))
    listener.listen()
    metadata = DaemonMetadata(
        executable=Path('/opt/recs/bin/recs'),
        platform=Platform.linux,
        gui_endpoint=str(endpoint),
    )

    assert gui_ipc.endpoint_reachable(metadata)


class FakeListener:
    def __init__(self, *, broken: bool = False) -> None:
        self.broken = broken
        self.closed = False
        self.messages: list[str] = []

    def write(self, message: str) -> bool:
        self.messages.append(message)
        return not self.broken

    def close(self) -> None:
        self.closed = True


def _eventually(check: t.Callable[[], bool]) -> bool:
    import time

    deadline = time.monotonic() + 1
    while time.monotonic() < deadline:
        if check():
            return True
        time.sleep(0.01)
    return False


def _socket_path() -> Path:
    return Path('/tmp') / f'recs-test-{uuid.uuid4().hex}.sock'
