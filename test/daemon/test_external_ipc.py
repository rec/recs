from pathlib import Path

import pytest
from reccy import rpc
from reccy.reccy import Reccy

from recs.daemon import external_ipc, gui_protocol


class FakeRpcServer:
    def __init__(
        self,
        control_endpoint: Path | str,
        event_endpoint: Path | str,
        handle: object,
        *,
        role: str,
    ) -> None:
        self.control_endpoint = control_endpoint
        self.event_endpoint = event_endpoint
        self.handle = handle
        self.role = role
        self.closed = False
        self.started = False
        self.published: list[tuple[str, dict[str, object]]] = []

    def start(self) -> None:
        self.started = True

    def close(self) -> None:
        self.closed = True

    def publish(self, name: str, **data: object) -> None:
        self.published.append((name, data))


def test_external_request_uses_recs_command_model() -> None:
    request = rpc.Request(
        id='request-1',
        command='set_cfg',
        params={'address': 'recording.longest_file_time', 'value': 3600},
    )

    message = external_ipc.recs_request(request)

    assert message == gui_protocol.SetCfg(
        type='set_cfg', address='recording.longest_file_time', value=3600
    )


def test_external_request_rejects_non_request_protocol_message() -> None:
    request = rpc.Request(id='request-1', command='rows', params={'rows': []})

    with pytest.raises(ValueError, match='Unsupported request: rows'):
        external_ipc.recs_request(request)


def test_external_response_preserves_recs_response_type() -> None:
    request = rpc.Request(id='request-1', command='get_cfg')

    result = external_ipc.response(
        request,
        gui_protocol.CfgValue(
            type='cfg_value', address='recording.longest_file_time', value=3600
        ),
    )

    assert result == rpc.Response(
        id='request-1',
        ok=True,
        result={
            'type': 'cfg_value',
            'address': 'recording.longest_file_time',
            'value': 3600,
        },
    )


def test_external_server_publishes_rows_and_shutdown_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created: list[FakeRpcServer] = []

    def make_server(
        control_endpoint: Path | str,
        event_endpoint: Path | str,
        handle: object,
        *,
        role: str,
    ) -> FakeRpcServer:
        server = FakeRpcServer(control_endpoint, event_endpoint, handle, role=role)
        created.append(server)
        return server

    monkeypatch.setattr(external_ipc.rpc, 'Server', make_server)
    server = external_ipc.ExternalServer(home=Path('/tmp'))

    server.start()
    server.publish_rows([{'device': 'Mic'}], [])
    server.close()

    assert created[0].started
    assert isinstance(server, Reccy)
    assert created[0].control_endpoint == Path('/tmp/.local/state/recs/control.sock')
    assert created[0].event_endpoint == Path('/tmp/.local/state/recs/events.sock')
    assert created[0].published == [
        ('rows', {'rows': [{'device': 'Mic'}], 'errors': []}),
        ('shutdown', {}),
        ('stopped', {}),
    ]
    assert created[0].closed


def test_external_server_releases_pending_request_when_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(external_ipc.rpc, 'Server', FakeRpcServer)
    server = external_ipc.ExternalServer(home=Path('/tmp'))
    server.start()
    request = external_ipc.ControlRequest(
        rpc.Request(id='request-1', command='get_cfg')
    )
    server._pending.append(request)

    server.close()

    assert request.wait() == rpc.Response(
        id='request-1', ok=False, message='recs is shutting down'
    )


def test_external_server_rejects_request_after_closing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(external_ipc.rpc, 'Server', FakeRpcServer)
    server = external_ipc.ExternalServer(home=Path('/tmp'))
    server.start()
    server.close()

    response = server.rpc_response(rpc.Request(id='request-1', command='get_cfg'))

    assert response == rpc.Response(
        id='request-1', ok=False, message='recs is shutting down'
    )
