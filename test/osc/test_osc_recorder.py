import json
import socket
import threading
import time
from pathlib import Path

import pytest

from recs.cfg.cfg import Cfg
from recs.osc import codec, recorder
from recs.osc.recorder import OscRecorder
from recs.ui.session_record import Record


class FakeSocket:
    def __init__(self) -> None:
        self.sent: list[tuple[bytes, tuple[str, int]]] = []
        self.received: list[tuple[bytes, tuple[str, int]]] = []
        self.bound: tuple[str, int] | None = None

    def bind(self, address: tuple[str, int]) -> None:
        self.bound = address

    def close(self) -> None:
        pass

    def getsockname(self) -> tuple[str, int]:
        return ('0.0.0.0', self.bound[1] if self.bound else 0)

    def recvfrom(self, size: int) -> tuple[bytes, tuple[str, int]]:
        if not self.received:
            raise BlockingIOError
        return self.received.pop(0)

    def sendto(self, data: bytes, target: tuple[str, int]) -> None:
        self.sent.append((data, target))

    def setblocking(self, value: bool) -> None:
        pass


def test_osc_recorder_does_not_open_outputs_in_preview_mode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = tmp_path / 'osc.toml'
    config.write_text(
        """[[nodes]]
name = "telemetry"
bind_port = 7000
"""
    )
    sockets: list[FakeSocket] = []
    monkeypatch.setattr(
        recorder.socket, 'socket', lambda *args: sockets.append(FakeSocket())
    )
    output_directory = tmp_path / 'session/osc'
    osc_recorder = OscRecorder(
        Cfg(output_directory=str(tmp_path), osc_nodes=config, silence_preview=True),
        output_directory,
        lambda warning: None,
        lambda record: None,
    )

    osc_recorder.start()
    osc_recorder.poll()

    assert sockets == []
    assert not output_directory.exists()


def test_subscription_records_inbound_packets_not_successful_renewals(
    tmp_path: Path, monkeypatch
) -> None:
    config = tmp_path / 'osc.toml'
    config.write_text(
        """[[nodes]]
name = "x18"
host = "10.43.0.18"
port = 10024

[[nodes.subscriptions]]
path = "/xremote"
resubscribe_period = 10
"""
    )
    fake_socket = FakeSocket()
    records: list[Record] = []
    warnings: list[str] = []
    monkeypatch.setattr(recorder.socket, 'socket', lambda *args: fake_socket)
    osc_recorder = OscRecorder(
        Cfg(output_directory=str(tmp_path), osc_nodes=config),
        tmp_path / 'session/osc',
        warnings.append,
        records.append,
    )

    osc_recorder.start()
    osc_recorder.poll()
    path = tmp_path / 'session/osc/x18.jsonl'

    assert fake_socket.sent == [
        (codec.encode_message('/xremote', []), ('10.43.0.18', 10024))
    ]
    assert path.read_text() == ''

    fake_socket.received.append(
        (codec.encode_message('/ch/01/mix/on', [True]), ('10.43.0.18', 10024))
    )
    fake_socket.received.append(
        (codec.encode_message('/ch/01/mix/on', [True]), ('10.43.0.18', 10024))
    )
    osc_recorder.poll()
    osc_recorder.stop()

    first, second = (json.loads(line) for line in path.read_text().splitlines())
    assert first['direction'] == 'in'
    assert first['decoded'] == [{'path': '/ch/01/mix/on', 'types': 'T', 'args': [True]}]
    assert second['kind'] == 'osc'
    assert second['endpoint'] == first['endpoint']
    assert second['ordinal'] == first['ordinal'] + 1
    assert warnings == []
    assert [record.type for record in records] == [
        'file_started',
        'osc_node_started',
        'file_finished',
    ]
    finished = records[-1]
    assert finished.quantity_count == 2
    assert first['direction'] == second['direction'] == 'in'
    assert finished.start_tick <= first['tick'] <= second['tick'] < finished.end_tick


def test_hostname_resolution_does_not_block_recording(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = tmp_path / 'osc.toml'
    config.write_text(
        """[[nodes]]
name = "mixer"
host = "mixer.local"
port = 10024

[[nodes.commands]]
path = "/xremote"
on_start = true
"""
    )
    resolution_started = threading.Event()
    allow_resolution = threading.Event()

    def getaddrinfo(*args: object, **kwargs: object) -> list[tuple[object, ...]]:
        resolution_started.set()
        allow_resolution.wait()
        return [(socket.AF_INET, socket.SOCK_DGRAM, 0, '', ('10.43.0.18', 10024))]

    fake_socket = FakeSocket()
    monkeypatch.setattr(recorder.socket, 'socket', lambda *args: fake_socket)
    monkeypatch.setattr(recorder.socket, 'getaddrinfo', getaddrinfo)
    osc_recorder = OscRecorder(
        Cfg(output_directory=str(tmp_path), osc_nodes=config),
        tmp_path / 'session/osc',
        lambda warning: None,
        lambda record: None,
    )

    osc_recorder.start()

    assert resolution_started.wait(1)
    assert fake_socket.sent == []
    allow_resolution.set()
    for _ in range(100):
        osc_recorder.poll()
        if fake_socket.sent:
            break
        time.sleep(0.001)
    osc_recorder.stop()

    assert fake_socket.sent == [
        (codec.encode_message('/xremote', []), ('10.43.0.18', 10024))
    ]


def test_hostname_resolution_failure_becomes_osc_warning(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = tmp_path / 'osc.toml'
    config.write_text(
        """[[nodes]]
name = "mixer"
host = "mixer.invalid"
port = 10024

[[nodes.polls]]
path = "/status"
period = 1
"""
    )

    def getaddrinfo(*args: object, **kwargs: object) -> list[tuple[object, ...]]:
        raise socket.gaierror('DNS unavailable')

    warnings: list[str] = []
    monkeypatch.setattr(recorder.socket, 'socket', lambda *args: FakeSocket())
    monkeypatch.setattr(recorder.socket, 'getaddrinfo', getaddrinfo)
    osc_recorder = OscRecorder(
        Cfg(output_directory=str(tmp_path), osc_nodes=config),
        tmp_path / 'session/osc',
        warnings.append,
        lambda record: None,
    )

    osc_recorder.start()
    for _ in range(100):
        osc_recorder.poll()
        if warnings:
            break
        time.sleep(0.001)
    osc_recorder.stop()

    assert warnings == ['OSC node mixer resolve failed: DNS unavailable']


def test_native_packets_are_independently_readable(tmp_path: Path, monkeypatch) -> None:
    config = tmp_path / 'osc.toml'
    config.write_text(
        """[[nodes]]
name = "telemetry"
bind_port = 7000
"""
    )
    fake_socket = FakeSocket()
    monkeypatch.setattr(recorder.socket, 'socket', lambda *args: fake_socket)
    osc_recorder = OscRecorder(
        Cfg(output_directory=str(tmp_path), osc_nodes=config),
        tmp_path / 'session/osc',
        lambda warning: None,
        lambda record: None,
    )

    osc_recorder.start()
    fake_socket.received.extend(
        [
            (codec.encode_message('/level', [0.5]), ('10.43.0.31', 7000)),
            (codec.encode_message('/level', [0.5]), ('10.43.0.31', 7000)),
        ]
    )
    osc_recorder.poll()
    osc_recorder.stop()

    lines = [
        json.loads(line)
        for line in (tmp_path / 'session/osc/telemetry.jsonl').read_text().splitlines()
    ]
    assert all('endpoint' in line for line in lines)
    assert [e['ordinal'] for e in lines] == [0, 1]


def test_osc_recorder_writes_packets_received_during_card_replacement(
    tmp_path: Path, monkeypatch
) -> None:
    config = tmp_path / 'osc.toml'
    config.write_text(
        """[[nodes]]
name = "telemetry"
bind_port = 7000
"""
    )
    fake_socket = FakeSocket()
    monkeypatch.setattr(recorder.socket, 'socket', lambda *args: fake_socket)
    osc_recorder = OscRecorder(
        Cfg(output_directory=str(tmp_path), osc_nodes=config),
        tmp_path / 'old/osc',
        lambda warning: None,
        lambda record: None,
    )

    osc_recorder.start()
    osc_recorder.suspend_for_card_replace()
    fake_socket.received.append(
        (codec.encode_message('/level', [0.5]), ('10.43.0.31', 7000))
    )
    osc_recorder.poll()
    osc_recorder.open_session(tmp_path / 'new/osc')
    osc_recorder.stop()

    lines = [
        json.loads(line)
        for line in (tmp_path / 'new/osc/telemetry.jsonl').read_text().splitlines()
    ]
    assert lines[0]['decoded'] == [{'path': '/level', 'types': 'f', 'args': [0.5]}]
