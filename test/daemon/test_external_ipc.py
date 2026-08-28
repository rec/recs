import threading
import time
from collections.abc import Callable
from pathlib import Path

import pytest
from reccy import rpc
from reccy.reccy import Reccy

from recs.base.waveform import (
    WaveformBatchData,
    WaveformLayoutData,
    WaveformTrackData,
    WaveformTrackLayout,
)
from recs.cfg.cfg import Cfg
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
        self.published_event = threading.Event()

    def start(self) -> None:
        self.started = True

    def close(self) -> None:
        self.closed = True

    def publish(self, name: str, **data: object) -> None:
        self.published.append((name, data))
        self.published_event.set()


class BlockingWaveformRpcServer(FakeRpcServer):
    def __init__(
        self,
        control_endpoint: Path | str,
        event_endpoint: Path | str,
        handle: object,
        *,
        role: str,
    ) -> None:
        super().__init__(control_endpoint, event_endpoint, handle, role=role)
        self.waveform_started = threading.Event()
        self.waveform_release = threading.Event()

    def publish(self, name: str, **data: object) -> None:
        super().publish(name, **data)
        if name == 'waveform_layout':
            self.waveform_started.set()
            self.waveform_release.wait()


def test_external_request_uses_recs_command_model() -> None:
    request = rpc.Request(
        command='set_cfg',
        params={'address': 'recording.longest_file_time', 'value': 3600},
    )

    message = external_ipc.recs_request(request)

    assert message == gui_protocol.SetCfg(
        type='set_cfg', address='recording.longest_file_time', value=3600
    )


def test_external_request_rejects_non_request_protocol_message() -> None:
    request = rpc.Request(command='rows', params={'rows': []})

    with pytest.raises(ValueError, match='Unsupported request: rows'):
        external_ipc.recs_request(request)


def test_external_request_uses_public_waveform_subscription() -> None:
    message = external_ipc.recs_request(rpc.Request(command='subscribe_waveforms'))

    assert message == gui_protocol.SubscribeWaveforms(type='subscribe_waveforms')


def test_external_response_preserves_recs_response_type() -> None:
    request = rpc.Request(command='get_cfg')

    result = external_ipc.response(
        request,
        gui_protocol.CfgValue(
            type='cfg_value', address='recording.longest_file_time', value=3600
        ),
    )

    assert result == {
        'type': 'cfg_value',
        'address': 'recording.longest_file_time',
        'value': 3600,
    }


def test_external_response_preserves_waveform_subscription() -> None:
    result = external_ipc.response(
        rpc.Request(command='subscribe_waveforms'),
        gui_protocol.WaveformSubscription(
            type='waveform_subscription',
            active=True,
            bucket_milliseconds=10,
            batch_milliseconds=40,
        ),
    )

    assert result == {
        'type': 'waveform_subscription',
        'active': True,
        'bucket_milliseconds': 10,
        'batch_milliseconds': 40,
    }


def test_external_server_publishes_subscribed_waveforms(
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
    layout = _waveform_layout()
    batch = _waveform_batch(0)
    server.start()

    server.publish_waveforms(layout, [batch])
    assert created[0].published == []
    subscription = server.set_waveform_subscription(
        True,
        Cfg(
            waveform_bucket_milliseconds=10,
            waveform_batch_milliseconds=40,
        ),
    )
    server.publish_waveforms(layout, [batch])

    assert _eventually(lambda: len(created[0].published) == 2)
    assert subscription == gui_protocol.WaveformSubscription(
        type='waveform_subscription',
        active=True,
        bucket_milliseconds=10,
        batch_milliseconds=40,
    )
    assert created[0].published == [
        ('waveform_layout', layout.model_dump()),
        ('waveform', batch.model_dump()),
    ]
    server.close()


def test_external_server_bounds_waveforms_while_event_connection_blocks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created: list[BlockingWaveformRpcServer] = []

    def make_server(
        control_endpoint: Path | str,
        event_endpoint: Path | str,
        handle: object,
        *,
        role: str,
    ) -> BlockingWaveformRpcServer:
        server = BlockingWaveformRpcServer(
            control_endpoint, event_endpoint, handle, role=role
        )
        created.append(server)
        return server

    monkeypatch.setattr(external_ipc.rpc, 'Server', make_server)
    server = external_ipc.ExternalServer(home=Path('/tmp'))
    server.start()
    server.set_waveform_subscription(True, Cfg())
    server.publish_waveforms(_waveform_layout(), [])
    assert created[0].waveform_started.wait(0.1)

    server.publish_waveforms(None, [_waveform_batch(i) for i in range(7)])
    created[0].waveform_release.set()

    assert _eventually(lambda: len(created[0].published) == 6)
    batches = [
        WaveformBatchData.model_validate(data)
        for name, data in created[0].published
        if name == 'waveform'
    ]
    assert [batch.sequence for batch in batches] == [2, 3, 4, 5, 6]
    assert sum(batch.dropped_batches for batch in batches) == 2
    server.close()


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
    request = external_ipc.ControlRequest(rpc.Request(command='get_cfg'))
    server._pending.append(request)

    server.close()

    assert request.wait().message == 'recs is shutting down'


def test_external_server_rejects_request_after_closing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(external_ipc.rpc, 'Server', FakeRpcServer)
    server = external_ipc.ExternalServer(home=Path('/tmp'))
    server.start()
    server.close()

    response = server.rpc_response(rpc.Request(command='get_cfg'))

    assert response.message == 'recs is shutting down'


def test_external_server_rejects_second_control_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(external_ipc.rpc, 'Server', FakeRpcServer)
    server = external_ipc.ExternalServer(home=Path('/tmp'))
    server.start()
    server._pending.append(external_ipc.ControlRequest(rpc.Request(command='get_cfg')))

    response = server.rpc_response(rpc.Request(command='status_snapshot'))

    assert response.message == 'recs already has an active control client'


def test_external_server_times_out_pending_control_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(external_ipc.rpc, 'Server', FakeRpcServer)
    server = external_ipc.ExternalServer(home=Path('/tmp'))
    server.start()
    monkeypatch.setattr(external_ipc, 'EXTERNAL_RESPONSE_TIMEOUT', 0)

    response = server.rpc_response(rpc.Request(command='status_snapshot'))

    assert response.message == 'recs did not answer before shutdown'
    assert server._pending == []


def _eventually(check: Callable[[], bool]) -> bool:
    deadline = time.monotonic() + 1
    while time.monotonic() < deadline:
        if check():
            return True
        time.sleep(0.01)
    return False


def _waveform_layout() -> WaveformLayoutData:
    return WaveformLayoutData(
        source='Mic',
        generation=1,
        sample_rate=48_000,
        bucket_frames=960,
        tracks=[WaveformTrackLayout(channels=[1], name='Vocal')],
    )


def _waveform_batch(sequence: int) -> WaveformBatchData:
    return WaveformBatchData(
        source='Mic',
        generation=1,
        sequence=sequence,
        sample_rate=48_000,
        bucket_frames=960,
        start_frame=sequence * 4_800,
        start_timestamp=100 + sequence / 10,
        present=[True] * 5,
        tracks=[
            WaveformTrackData(
                channels=[1],
                minimum=[[-0.1] * 5],
                maximum=[[0.1] * 5],
            )
        ],
    )
