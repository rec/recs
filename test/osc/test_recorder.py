import json
from pathlib import Path

from recs.cfg.cfg import Cfg
from recs.osc import codec, recorder
from recs.osc.recorder import OscRecorder
from recs.ui.session_manifest import ManifestRecord


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
    records: list[ManifestRecord] = []
    warnings: list[str] = []
    monkeypatch.setattr(recorder.socket, 'socket', lambda *args: fake_socket)
    osc_recorder = OscRecorder(
        Cfg(output_directory=str(tmp_path), osc_nodes=config),
        tmp_path / 'session',
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
    osc_recorder.poll()
    osc_recorder.stop()

    line = json.loads(path.read_text())
    assert line['direction'] == 'in'
    assert line['decoded'] == [{'path': '/ch/01/mix/on', 'types': 'T', 'args': [True]}]
    assert warnings == []
    assert [record.type for record in records] == [
        'file_started',
        'osc_node_started',
        'file_finished',
    ]
