import typing as t
from pathlib import Path

import pytest
from pydantic import ValidationError

from recs.base import RecsError
from recs.cfg import Cfg
from recs.daemon import gui_ipc
from recs.daemon.gui_protocol import (
    Command,
    Hello,
    RowsMessage,
    Shutdown,
    parse_message,
)
from recs.daemon.models import DaemonMetadata, Platform
from recs.ui.key_events import KeyEvent


def test_protocol_parses_valid_messages() -> None:
    message = parse_message('{"type":"rows","rows":[{"device":"Mic"}]}')

    assert isinstance(message, RowsMessage)
    assert message.rows == [{'device': 'Mic'}]
    assert message.errors == []


def test_protocol_parses_daemon_hello() -> None:
    message = parse_message('{"type":"hello","role":"daemon","version":1}')

    assert isinstance(message, Hello)
    assert message.role == 'daemon'


def test_protocol_parses_calibrate_command() -> None:
    message = parse_message('{"type":"command","id":"c1","command":"calibrate"}')

    assert isinstance(message, Command)
    assert message.command == 'calibrate'


def test_protocol_parses_app_specific_command_names() -> None:
    message = parse_message('{"type":"command","id":"c1","command":"reload_config"}')

    assert isinstance(message, Command)
    assert message.command == 'reload_config'


def test_protocol_parses_command_fields() -> None:
    message = parse_message(
        '{"type":"command","id":"c1","command":"set_noise_floor",'
        '"source":"Mic","noise_floor":42.5}'
    )

    assert isinstance(message, Command)
    assert message.source == 'Mic'
    assert message.noise_floor == 42.5


def test_protocol_parses_track_names_command() -> None:
    message = parse_message(
        '{"type":"command","id":"c1","command":"set_track_names",'
        '"track_names":{"Mic":{"Lead Vocal":1}}}'
    )

    assert isinstance(message, Command)
    assert message.track_names == {'Mic': {'Lead Vocal': 1}}


def test_protocol_parses_shutdown() -> None:
    message = parse_message('{"type":"shutdown"}')

    assert isinstance(message, Shutdown)


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

    server.broadcast([{'device': 'Mic'}], ['Device Mic failed'])

    assert first.messages == [
        '{"type":"rows","rows":[{"device":"Mic"}],"errors":["Device Mic failed"]}\n'
    ]
    assert second.messages == first.messages


def test_daemon_publisher_removes_broken_listeners() -> None:
    server = gui_ipc.DaemonGuiServer(lambda: iter([{'device': 'Mic'}]), Cfg())
    good = FakeListener()
    broken = FakeListener(broken=True)
    server.clients = [good, broken]

    server.broadcast([{'device': 'Mic'}], [])

    assert server.clients == [good]
    assert broken.closed


def test_daemon_publisher_sends_shutdown_when_stopped() -> None:
    server = gui_ipc.DaemonGuiServer(lambda: iter([]), Cfg())
    first = FakeListener()
    second = FakeListener()
    server.clients = [first, second]

    server.stop()

    assert first.messages == ['{"type":"shutdown"}\n']
    assert second.messages == first.messages
    assert first.closed
    assert second.closed


def test_daemon_publisher_ignores_second_shutdown() -> None:
    server = gui_ipc.DaemonGuiServer(lambda: iter([]), Cfg())
    listener = FakeListener()
    server.clients = [listener]

    server.request_shutdown()
    server.request_shutdown()

    assert listener.messages == ['{"type":"shutdown"}\n']
    assert listener.closed


def test_daemon_publisher_writes_gui_ipc_error_status(tmp_path: Path) -> None:
    server = gui_ipc.DaemonGuiServer(lambda: iter([]), Cfg())
    server.enabled = True
    server.paths = server.paths.model_copy(update={'status': tmp_path / 'status.json'})
    server.backend = BrokenBackend()

    server.start()

    assert 'address in use' in server.paths.status.read_text()


def test_daemon_publisher_writes_health_rows(tmp_path: Path) -> None:
    server = gui_ipc.DaemonGuiServer(
        lambda: iter([{'device': 'Mic'}]),
        Cfg(),
        errors=lambda: ['Device Mic failed'],
    )
    server.enabled = True
    server.paths = server.paths.model_copy(update={'status': tmp_path / 'status.json'})

    server.update()

    assert '"rows":[{"device":"Mic"}]' in server.paths.status.read_text()
    assert '"errors":["Device Mic failed"]' in server.paths.status.read_text()


def test_gui_listener_replies_to_supported_hello() -> None:
    connection = FakeConnection(['{"type":"hello","role":"gui","version":1}\n'])
    listener = gui_ipc.GuiListener(connection, lambda event: None)

    listener._read()

    assert connection.sent == ['{"type":"hello","role":"daemon","version":1}\n']


def test_gui_listener_accepts_key_events_after_hello() -> None:
    events: list[KeyEvent] = []
    connection = FakeConnection(
        [
            '{"type":"hello","role":"gui","version":1}\n',
            '{"type":"key_pressed","key":"g"}\n',
        ]
    )
    listener = gui_ipc.GuiListener(connection, events.append)

    listener._read()

    assert events == [KeyEvent(type='key_pressed', key='g')]


def test_gui_listener_queues_commands_after_hello() -> None:
    requests: list[gui_ipc.ControlRequest] = []
    connection = FakeConnection(
        [
            '{"type":"hello","role":"gui","version":1}\n',
            '{"type":"command","id":"c1","command":"calibrate"}\n',
        ]
    )
    listener = gui_ipc.GuiListener(connection, lambda event: None, requests.append)

    listener._read()
    requests[0].reply(ok=True, result={'profiles': {'Mic': {'noise_floor': 15.0}}})

    assert requests[0].command.id == 'c1'
    assert connection.sent == [
        '{"type":"hello","role":"daemon","version":1}\n',
        (
            '{"type":"reply","id":"c1","ok":true,'
            '"result":{"profiles":{"Mic":{"noise_floor":15.0}}}}\n'
        ),
    ]


def test_client_shutdown_propagates_to_all_listeners() -> None:
    server = gui_ipc.DaemonGuiServer(lambda: iter([]), Cfg())
    first = FakeConnection(
        [
            '{"type":"hello","role":"gui","version":1}\n',
            '{"type":"shutdown"}\n',
            '{"type":"shutdown"}\n',
        ]
    )
    second = FakeListener()
    first_listener = gui_ipc.GuiListener(
        first,
        lambda event: None,
        request_shutdown=server.request_shutdown,
    )
    server.clients = [first_listener, second]

    first_listener._read()

    assert server.closed
    assert first.sent == [
        '{"type":"hello","role":"daemon","version":1}\n',
        '{"type":"shutdown"}\n',
    ]
    assert first.closed
    assert second.messages == ['{"type":"shutdown"}\n']
    assert second.closed


def test_gui_listener_rejects_key_events_before_hello() -> None:
    events: list[KeyEvent] = []
    connection = FakeConnection(['{"type":"key_pressed","key":"g"}\n'])
    listener = gui_ipc.GuiListener(connection, events.append)

    listener._read()

    assert connection.sent == [
        '{"type":"error","message":"GUI hello required before other messages"}\n'
    ]
    assert connection.closed
    assert events == []


def test_gui_listener_rejects_unsupported_hello() -> None:
    connection = FakeConnection(['{"type":"hello","role":"gui","version":2}\n'])
    listener = gui_ipc.GuiListener(connection, lambda event: None)

    listener._read()

    assert connection.sent == [
        (
            '{"type":"error","message":"GUI protocol version 2 is not supported; '
            'daemon requires 1"}\n'
        )
    ]
    assert connection.closed


def test_remote_row_provider_exposes_latest_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = FakeConnection(['{"type":"rows","rows":[{"device":"Mic"}]}\n'])
    monkeypatch.setattr(gui_ipc, 'client_connection', lambda endpoint: connection)

    client = gui_ipc.RemoteGuiClient(Path('/tmp/recs.sock'))
    client.start()
    assert _eventually(lambda: list(client.rows()) == [{'device': 'Mic'}])


def test_remote_row_provider_exposes_latest_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = FakeConnection(
        ['{"type":"rows","rows":[],"errors":["Device Mic failed"]}\n']
    )
    monkeypatch.setattr(gui_ipc, 'client_connection', lambda endpoint: connection)

    client = gui_ipc.RemoteGuiClient(Path('/tmp/recs.sock'))
    client.start()

    assert _eventually(lambda: client.errors() == ['Device Mic failed'])


def test_remote_row_provider_closes_on_protocol_error(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    connection = FakeConnection(
        ['{"type":"error","message":"GUI protocol version 2 is not supported"}\n']
    )
    monkeypatch.setattr(gui_ipc, 'client_connection', lambda endpoint: connection)
    client = gui_ipc.RemoteGuiClient(Path('/tmp/recs.sock'))

    client.start()

    assert _eventually(lambda: client.closed)
    assert capsys.readouterr().err == 'GUI protocol version 2 is not supported\n'


def test_remote_row_provider_closes_on_shutdown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = FakeConnection(['{"type":"shutdown"}\n'])
    monkeypatch.setattr(gui_ipc, 'client_connection', lambda endpoint: connection)
    client = gui_ipc.RemoteGuiClient(Path('/tmp/recs.sock'))

    client.start()

    assert _eventually(lambda: client.closed)


def test_remote_row_provider_sends_key_events(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = FakeConnection()
    monkeypatch.setattr(gui_ipc, 'client_connection', lambda endpoint: connection)

    client = gui_ipc.RemoteGuiClient(Path('/tmp/recs.sock'))
    client.start()
    client.record_key(KeyEvent(type='key_pressed', key='g'))

    assert '{"type":"key_pressed","key":"g"}\n' in connection.sent


def test_remote_row_provider_sends_shutdown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = FakeConnection()
    monkeypatch.setattr(gui_ipc, 'client_connection', lambda endpoint: connection)

    client = gui_ipc.RemoteGuiClient(Path('/tmp/recs.sock'))
    client.start()
    client.shutdown()

    assert '{"type":"shutdown"}\n' in connection.sent


def test_remote_row_provider_fails_when_hello_cannot_be_sent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = FakeConnection(broken=True)
    monkeypatch.setattr(gui_ipc, 'client_connection', lambda endpoint: connection)

    client = gui_ipc.RemoteGuiClient(Path('/tmp/recs.sock'))

    with pytest.raises(BrokenPipeError, match='Could not send GUI hello'):
        client.start()

    assert client.closed


def test_endpoint_reachable_checks_metadata_socket(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = FakeConnection()
    metadata = DaemonMetadata(
        executable=Path('/opt/recs/bin/recs'),
        platform=Platform.linux,
        gui_endpoint='/tmp/recs.sock',
    )

    monkeypatch.setattr(gui_ipc, 'client_connection', lambda endpoint: connection)

    assert gui_ipc.endpoint_reachable(metadata)
    assert connection.closed


def test_endpoint_reachable_checks_windows_pipe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connections: list[FakeConnection] = []
    metadata = DaemonMetadata(
        executable=Path('/opt/recs/bin/recs'),
        platform=Platform.windows,
        gui_endpoint=gui_ipc.WINDOWS_PIPE,
    )

    def connect(endpoint: str | Path) -> FakeConnection:
        assert endpoint == gui_ipc.WINDOWS_PIPE
        connection = FakeConnection()
        connections.append(connection)
        return connection

    monkeypatch.setattr(gui_ipc, 'client_connection', connect)

    assert gui_ipc.endpoint_reachable(metadata)
    assert connections[0].closed


def test_run_remote_gui_reports_connection_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    metadata = DaemonMetadata(
        executable=Path('/opt/recs/bin/recs'),
        platform=Platform.linux,
        gui_endpoint='/tmp/recs.sock',
    )

    def connect(endpoint: str | Path) -> FakeConnection:
        raise OSError('connection refused')

    monkeypatch.setattr(gui_ipc, 'client_connection', connect)

    with pytest.raises(RecsError, match='Could not connect to daemon GUI'):
        gui_ipc.run_remote_gui(metadata, Cfg(gui=True))


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


class BrokenBackend:
    def start(self) -> None:
        raise OSError('address in use')

    def accept(self) -> None:
        return None

    def close(self) -> None:
        pass


class FakeConnection:
    def __init__(
        self,
        received: list[str] | None = None,
        *,
        broken: bool = False,
    ) -> None:
        self.broken = broken
        self.closed = False
        self.received = received or []
        self.sent: list[str] = []

    def read_lines(self) -> t.Iterator[str]:
        return iter(self.received)

    def write(self, message: str) -> bool:
        self.sent.append(message)
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
