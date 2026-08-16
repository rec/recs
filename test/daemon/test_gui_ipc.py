import json
import threading
import time
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from pydantic import ValidationError
from reccy.models import Platform

from recs.base.errors import ErrorRecord, RecsError
from recs.cfg.cfg import Cfg
from recs.daemon import gui_backend, gui_ipc, gui_protocol
from recs.daemon.models import DaemonMetadata, DaemonStatus
from recs.ui.key_events import KeyEvent


def test_protocol_parses_valid_messages() -> None:
    message = gui_protocol.parse_message('{"type":"rows","rows":[{"device":"Mic"}]}')

    assert isinstance(message, gui_protocol.RowsMessage)
    assert message.rows == [{'device': 'Mic'}]
    assert message.errors == []


def test_protocol_parses_daemon_hello() -> None:
    message = gui_protocol.parse_message('{"type":"hello","role":"daemon","version":3}')

    assert isinstance(message, gui_protocol.Hello)
    assert message.role == 'daemon'


def test_protocol_parses_calibrate_request() -> None:
    message = gui_protocol.parse_message('{"type":"calibrate"}')

    assert isinstance(message, gui_protocol.Calibrate)
    assert message.channels == {}


def test_protocol_parses_selected_calibration_request() -> None:
    message = gui_protocol.parse_message(
        '{"type":"calibrate","channels":{"Mic":[1,3]}}'
    )

    assert isinstance(message, gui_protocol.Calibrate)
    assert message.channels == {'Mic': [1, 3]}


def test_protocol_rejects_unknown_requests() -> None:
    with pytest.raises(ValidationError):
        gui_protocol.parse_message('{"type":"reload_config"}')


def test_protocol_parses_set_noise_floor_request() -> None:
    message = gui_protocol.parse_message(
        '{"type":"set_noise_floor","source":"Mic","channel":1,"noise_floor":42.5}'
    )

    assert isinstance(message, gui_protocol.SetNoiseFloor)
    assert message.source == 'Mic'
    assert message.channel == 1
    assert message.noise_floor == 42.5


def test_protocol_parses_set_track_names_request() -> None:
    message = gui_protocol.parse_message(
        '{"type":"set_track_names","track_names":{"Mic":{"Lead Vocal":1}}}'
    )

    assert isinstance(message, gui_protocol.SetTrackNames)
    assert message.track_names == {'Mic': {'Lead Vocal': 1}}


def test_protocol_parses_set_tracks_request() -> None:
    message = gui_protocol.parse_message(
        '{"type":"set_tracks","source":"Mic","tracks":['
        '{"channels":[15],"name":"VL"},{"channels":[16]}]}'
    )

    assert isinstance(message, gui_protocol.SetTracks)
    assert message.source == 'Mic'
    assert message.tracks == [
        gui_protocol.ChannelTrack(channels=[15], name='VL'),
        gui_protocol.ChannelTrack(channels=[16]),
    ]


def test_protocol_parses_mutable_attributes_request() -> None:
    message = gui_protocol.parse_message('{"type":"mutable_attributes"}')

    assert isinstance(message, gui_protocol.MutableAttributes)


def test_protocol_parses_shutdown() -> None:
    message = gui_protocol.parse_message('{"type":"shutdown"}')

    assert isinstance(message, gui_protocol.Shutdown)


def test_protocol_rejects_malformed_messages() -> None:
    with pytest.raises(ValidationError):
        gui_protocol.parse_message('{"type":"rows"}')


def test_protocol_rejects_unknown_key_messages() -> None:
    with pytest.raises(ValidationError):
        gui_protocol.parse_message('{"type":"unknown","key":"g"}')


def test_daemon_publisher_broadcasts_rows_to_listeners() -> None:
    server = gui_ipc.DaemonGuiServer(lambda: iter([{'device': 'Mic'}]), Cfg())
    first = FakeListener()
    second = FakeListener()
    server.clients = [first, second]

    server.broadcast(
        [{'device': 'Mic'}],
        [
            ErrorRecord(
                timestamp='2026-08-13T12:34:56.789Z', message='Device Mic failed'
            )
        ],
    )

    assert first.messages == [
        '{"type":"rows","rows":[{"device":"Mic"}],"errors":['
        '{"timestamp":"2026-08-13T12:34:56.789Z","message":"Device Mic failed"}]}\n'
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


def test_daemon_publisher_releases_pending_control_requests_on_shutdown() -> None:
    server = gui_ipc.DaemonGuiServer(lambda: iter([]), Cfg())
    request = gui_ipc.ControlRequest(gui_protocol.Calibrate(type='calibrate'))
    server.control_requests = [request]

    server.request_shutdown()

    assert request.wait_for_response() == gui_protocol.RecordingState(
        type='recording_state', paused=False, stopped=True
    )


def test_control_request_wait_times_out() -> None:
    request = gui_ipc.ControlRequest(gui_protocol.Calibrate(type='calibrate'))

    assert request.wait_for_response(timeout=0) == gui_protocol.Error(
        type='error', message='recs did not answer before shutdown'
    )


def test_daemon_publisher_rejects_second_gui_client() -> None:
    server = gui_ipc.DaemonGuiServer(lambda: iter([]), Cfg())
    existing = FakeListener()
    rejected = FakeConnection()
    server.clients = [existing]
    server.backend = SingleAcceptBackend(rejected, server)
    server.running = True

    server._accept()

    assert rejected.sent == [
        '{"type":"error","message":"recs already has an active GUI client"}\n'
    ]
    assert rejected.closed
    assert server.clients == [existing]


def test_daemon_publisher_writes_gui_ipc_error_status(tmp_path: Path) -> None:
    server = gui_ipc.DaemonGuiServer(lambda: iter([]), Cfg())
    server.enabled = True
    server.paths = server.paths.model_copy(update={'status': tmp_path / 'status.json'})
    server.backend = BrokenBackend()

    server.start()

    assert 'address in use' in server.paths.status.read_text()


def test_daemon_publisher_writes_health_rows(tmp_path: Path) -> None:
    published: list[tuple[list[dict[str, object]], list[ErrorRecord]]] = []
    server = gui_ipc.DaemonGuiServer(
        lambda: iter([{'device': 'Mic'}]),
        Cfg(),
        errors=lambda: [
            ErrorRecord(
                timestamp='2026-08-13T12:34:56.789Z', message='Device Mic failed'
            )
        ],
        external_rows=lambda rows, errors: published.append((rows, errors)),
    )
    server.enabled = True
    server.paths = server.paths.model_copy(update={'status': tmp_path / 'status.json'})

    server.update()

    content = server.paths.status.read_text()
    json.loads(content)
    assert '"rows":[{"device":"Mic"}]' in content
    assert '"timestamp":"2026-08-13T12:34:56.789Z"' in content
    assert '"message":"Device Mic failed"' in content
    assert not server.paths.status.with_name('.status.json.tmp').exists()
    assert published == [
        (
            [{'device': 'Mic'}],
            [
                ErrorRecord(
                    timestamp='2026-08-13T12:34:56.789Z',
                    message='Device Mic failed',
                )
            ],
        )
    ]


def test_daemon_publisher_limits_status_file_writes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = 0.0
    server = gui_ipc.DaemonGuiServer(lambda: iter([]), Cfg())
    server.enabled = True
    writes: list[DaemonStatus] = []

    monkeypatch.setattr(gui_ipc.time, 'monotonic', lambda: now)
    monkeypatch.setattr(
        gui_ipc, '_write_status', lambda path, status: writes.append(status)
    )

    server.update()
    now = 0.5
    server.update()
    now = 1.0
    server.update()

    assert len(writes) == 2


def test_status_write_is_not_synchronized(monkeypatch: pytest.MonkeyPatch) -> None:
    synchronizations: list[bool] = []

    def write_json_model(
        path: Path, status: DaemonStatus, *, sync: bool = True
    ) -> None:
        synchronizations.append(sync)

    monkeypatch.setattr(gui_ipc.settings, 'write_json_model', write_json_model)

    gui_ipc._write_status(Path('/tmp/status.json'), DaemonStatus())

    assert synchronizations == [False]


def test_gui_listener_replies_to_supported_hello() -> None:
    connection = FakeConnection(['{"type":"hello","role":"gui","version":3}\n'])
    listener = gui_ipc.GuiListener(connection, lambda event: None)

    listener._read()

    assert connection.sent == ['{"type":"hello","role":"daemon","version":3}\n']


def test_gui_listener_accepts_key_events_after_hello() -> None:
    events: list[KeyEvent] = []
    connection = FakeConnection(
        [
            '{"type":"hello","role":"gui","version":3}\n',
            '{"type":"key_pressed","key":"g"}\n',
        ]
    )
    listener = gui_ipc.GuiListener(connection, events.append)

    listener._read()

    assert events == [KeyEvent(type='key_pressed', key='g')]


def test_gui_listener_returns_direct_response_after_hello() -> None:
    def respond(request: gui_ipc.ControlRequest) -> None:
        request.respond(
            gui_protocol.Calibrated(
                type='calibrated',
                measurements={},
                noise_floors={'Mic': {'1': 15.0}},
            )
        )

    connection = FakeConnection(
        [
            '{"type":"hello","role":"gui","version":3}\n',
            '{"type":"calibrate"}\n',
        ]
    )
    listener = gui_ipc.GuiListener(connection, lambda event: None, respond)

    listener._read()

    assert connection.sent == [
        '{"type":"hello","role":"daemon","version":3}\n',
        (
            '{"type":"calibrated","measurements":{},'
            '"noise_floors":{"Mic":{"1":15.0}}}\n'
        ),
    ]


def test_gui_listener_queues_row_writes_when_connection_blocks() -> None:
    connection = BlockingWriteConnection()
    listener = gui_ipc.GuiListener(connection, lambda event: None)
    listener.start()

    assert listener.write('first\n')
    assert connection.started.wait(0.1)
    start = time.monotonic()
    assert listener.write('second\n')

    assert time.monotonic() - start < 0.1
    connection.release.set()
    assert _eventually(lambda: connection.sent == ['first\n', 'second\n'])
    listener.close()


def test_client_shutdown_propagates_to_all_listeners() -> None:
    server = gui_ipc.DaemonGuiServer(lambda: iter([]), Cfg())
    first = FakeConnection(
        [
            '{"type":"hello","role":"gui","version":3}\n',
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
        '{"type":"hello","role":"daemon","version":3}\n',
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
    connection = FakeConnection(['{"type":"hello","role":"gui","version":1}\n'])
    listener = gui_ipc.GuiListener(connection, lambda event: None)

    listener._read()

    assert connection.sent == [
        (
            '{"type":"error","message":"GUI protocol version 1 is not supported; '
            'daemon requires 3"}\n'
        )
    ]
    assert connection.closed


def test_remote_row_provider_exposes_latest_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = FakeConnection(['{"type":"rows","rows":[{"device":"Mic"}]}\n'])
    monkeypatch.setattr(gui_backend, 'client_connection', lambda endpoint: connection)

    client = gui_ipc.RemoteGuiClient(Path('/tmp/recs.sock'))
    client.start()
    assert _eventually(lambda: list(client.rows()) == [{'device': 'Mic'}])


def test_remote_row_provider_exposes_latest_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = FakeConnection(
        [
            '{"type":"rows","rows":[],"errors":['
            '{"timestamp":"2026-08-13T12:34:56.789Z",'
            '"message":"Device Mic failed"}]}\n'
        ]
    )
    monkeypatch.setattr(gui_backend, 'client_connection', lambda endpoint: connection)

    client = gui_ipc.RemoteGuiClient(Path('/tmp/recs.sock'))
    client.start()

    assert _eventually(lambda: client.errors() == ['Device Mic failed'])


def test_remote_row_provider_closes_on_protocol_error(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    connection = FakeConnection(
        ['{"type":"error","message":"GUI protocol version 3 is not supported"}\n']
    )
    monkeypatch.setattr(gui_backend, 'client_connection', lambda endpoint: connection)
    client = gui_ipc.RemoteGuiClient(Path('/tmp/recs.sock'))

    client.start()

    assert _eventually(lambda: client.closed)
    assert caplog.messages == ['GUI protocol version 3 is not supported']


def test_remote_row_provider_closes_on_shutdown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = FakeConnection(['{"type":"shutdown"}\n'])
    monkeypatch.setattr(gui_backend, 'client_connection', lambda endpoint: connection)
    client = gui_ipc.RemoteGuiClient(Path('/tmp/recs.sock'))

    client.start()

    assert _eventually(lambda: client.closed)


def test_remote_row_provider_sends_key_events(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = FakeConnection()
    monkeypatch.setattr(gui_backend, 'client_connection', lambda endpoint: connection)

    client = gui_ipc.RemoteGuiClient(Path('/tmp/recs.sock'))
    client.start()
    client.record_key(KeyEvent(type='key_pressed', key='g'))

    assert '{"type":"key_pressed","key":"g"}\n' in connection.sent


def test_remote_row_provider_sends_shutdown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = FakeConnection()
    monkeypatch.setattr(gui_backend, 'client_connection', lambda endpoint: connection)

    client = gui_ipc.RemoteGuiClient(Path('/tmp/recs.sock'))
    client.start()
    client.shutdown()

    assert '{"type":"shutdown"}\n' in connection.sent


def test_remote_row_provider_fails_when_hello_cannot_be_sent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = FakeConnection(broken=True)
    monkeypatch.setattr(gui_backend, 'client_connection', lambda endpoint: connection)

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

    monkeypatch.setattr(gui_backend, 'client_connection', lambda endpoint: connection)

    assert gui_ipc.endpoint_reachable(metadata)
    assert connection.closed


def test_endpoint_reachable_checks_windows_pipe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connections: list[FakeConnection] = []
    metadata = DaemonMetadata(
        executable=Path('/opt/recs/bin/recs'),
        platform=Platform.windows,
        gui_endpoint=gui_backend.WINDOWS_PIPE,
    )

    def connect(endpoint: str | Path) -> FakeConnection:
        assert endpoint == gui_backend.WINDOWS_PIPE
        connection = FakeConnection()
        connections.append(connection)
        return connection

    monkeypatch.setattr(gui_backend, 'client_connection', connect)

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

    monkeypatch.setattr(gui_backend, 'client_connection', connect)

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


class SingleAcceptBackend:
    def __init__(
        self, connection: 'FakeConnection', server: gui_ipc.DaemonGuiServer
    ) -> None:
        self.connection = connection
        self.server = server

    def accept(self) -> 'FakeConnection':
        self.server.running = False
        return self.connection


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

    def read_lines(self) -> Iterator[str]:
        return iter(self.received)

    def write(self, message: str) -> bool:
        self.sent.append(message)
        return not self.broken

    def close(self) -> None:
        self.closed = True


class BlockingWriteConnection(FakeConnection):
    def __init__(self) -> None:
        super().__init__()
        self.started = threading.Event()
        self.release = threading.Event()

    def write(self, message: str) -> bool:
        self.started.set()
        self.release.wait()
        return super().write(message)

    def close(self) -> None:
        self.release.set()
        super().close()


def _eventually(check: Callable[[], bool]) -> bool:
    import time

    deadline = time.monotonic() + 1
    while time.monotonic() < deadline:
        if check():
            return True
        time.sleep(0.01)
    return False
