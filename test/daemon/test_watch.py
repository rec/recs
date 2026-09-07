import json
from collections.abc import Callable

import pytest
from reccy.protocol import rpc

from recs.daemon import watch


class FakeEventClient:
    def __init__(
        self,
        endpoint: object,
        receive: Callable[[rpc.Event], None],
        *,
        role: str,
    ) -> None:
        self.endpoint = endpoint
        self.receive = receive
        self.role = role
        self.closed = False

    def start(self) -> None:
        self.receive(
            rpc.Event(
                name='rows',
                data={
                    'rows': [{'device': 'Mic', 'buffer': 0.25, 'dropped': 12}],
                    'errors': [{'message': 'awaiting card', 'value': True}],
                },
            )
        )
        self.receive(rpc.Event(name='stopped'))

    def close(self) -> None:
        self.closed = True


class FakeControlClient:
    def __init__(self, endpoint: object, *, role: str) -> None:
        self.endpoint = endpoint
        self.role = role

    def call(self, command: str) -> dict[str, object]:
        assert command == 'status_snapshot'
        return {
            'type': 'status_snapshot_result',
            'recording': {'paused': False},
            'session_directory': '/recordings/session',
            'disk': {
                'free_bytes': 1_000,
                'estimated_seconds_remaining': 30.0,
            },
            'rows': [],
            'errors': [],
        }


def test_json_watch_subscribes_before_snapshot_and_stops(
    capsys: pytest.CaptureFixture[str],
) -> None:
    result = watch.watch(
        watch.Watch(json_output=True),
        FakeEventClient,
        FakeControlClient,
    )

    assert result == 0
    lines = capsys.readouterr().out.splitlines()
    assert json.loads(lines[0])['type'] == 'status_snapshot_result'
    assert json.loads(lines[1])['name'] == 'rows'
    assert json.loads(lines[2])['name'] == 'stopped'
