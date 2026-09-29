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
        self.terminal_reason: rpc.EventCloseReason | None = None

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

    def wait_closed(self, timeout: float | None = None) -> bool:
        return self.closed


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


def test_watch_reports_event_stream_closure_without_stop(
    capsys: pytest.CaptureFixture[str],
) -> None:
    class DisconnectedEventClient(FakeEventClient):
        def start(self) -> None:
            self.terminal_reason = rpc.EventCloseReason.peer_eof

        def wait_closed(self, timeout: float | None = None) -> bool:
            return True

    result = watch.watch(
        watch.Watch(json_output=True),
        DisconnectedEventClient,
        FakeControlClient,
    )

    output = capsys.readouterr()
    assert result == 1
    assert json.loads(output.out.splitlines()[0])['type'] == 'status_snapshot_result'
    assert 'event stream closed' in output.err
    assert 'peer_eof' in output.err


def test_watch_reports_event_overflow_before_snapshot() -> None:
    watcher = watch.StatusWatcher(json_output=True)
    for _ in range(watch.MAX_PENDING_EVENTS + 1):
        watcher.receive(rpc.Event(name='rows'))

    assert watcher.pending is not None
    assert len(watcher.pending) == watch.MAX_PENDING_EVENTS
    with pytest.raises(ConnectionError, match='Too many events'):
        watcher.set_snapshot({})


@pytest.mark.parametrize('arguments', [['--help'], ['--instance', '123', '--help']])
def test_watch_help_does_not_discover_or_connect_to_instances(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    arguments: list[str],
) -> None:
    monkeypatch.setattr(
        watch.instances, 'resolve', lambda selector: pytest.fail('Instance discovery')
    )
    monkeypatch.setattr(
        watch, 'watch', lambda *args, **kwargs: pytest.fail('Connection')
    )

    with pytest.raises(SystemExit) as result:
        watch.main(arguments)

    assert result.value.code == 0
    assert 'usage: recs watch' in capsys.readouterr().out
