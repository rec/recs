import subprocess
from typing import cast

import pytest

from recs.cfg import device
from recs.ui import device_poller
from recs.ui.device_poller import DevicePoller, DeviceQueryStream


class FakeQueryStream:
    def __init__(self) -> None:
        self.snapshots: list[list[device.DeviceDict]] = [
            [
                {'max_input_channels': 1, 'name': 'Mic'},
                {'max_input_channels': 0, 'name': 'Speaker'},
            ],
            [{'max_input_channels': 2, 'name': 'Interface'}],
        ]
        self.started = False
        self.stopped = False

    def start(self) -> None:
        self.started = True

    def stop(self) -> None:
        self.stopped = True

    def devices(self) -> list[device.DeviceDict] | None:
        if self.snapshots:
            return self.snapshots.pop(0)
        return None


class FakeDeadProcess:
    stdout = None

    def poll(self) -> int:
        return 1


class FakeLiveProcess:
    stdout = None

    def poll(self) -> None:
        return None


class FakeUnresponsiveProcess:
    def __init__(self) -> None:
        self.killed = False
        self.stdout = FakeStdout()

    def terminate(self) -> None:
        pass

    def wait(self, timeout: float | None = None) -> None:
        if not self.killed:
            raise subprocess.TimeoutExpired(['recs', 'query-devices-stream'], timeout)

    def kill(self) -> None:
        self.killed = True


class FakeStdout:
    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


def test_poller_keeps_only_latest_input_devices(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(device_poller, 'DeviceQueryStream', FakeQueryStream)
    poller = DevicePoller(1)

    poller.poll()
    poller.poll()

    assert poller.latest() == {
        'Interface': {'max_input_channels': 2, 'name': 'Interface'}
    }
    assert poller.latest() is None


def test_poller_starts_and_stops_query_stream(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(device_poller, 'DeviceQueryStream', FakeQueryStream)
    poller = DevicePoller(0.01)

    poller.start()
    poller.stop()
    poller.join(1)

    assert poller.query_stream.started
    assert poller.query_stream.stopped


def test_query_stream_restarts_when_process_exits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    restarted = False
    stream = DeviceQueryStream()
    stream.process = cast(subprocess.Popen[str], FakeDeadProcess())

    def restart() -> None:
        nonlocal restarted
        restarted = True

    monkeypatch.setattr(stream, 'restart', restart)

    assert stream.devices() is None
    assert restarted


def test_query_stream_restarts_when_updates_stop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    restarted = False
    stream = DeviceQueryStream()
    stream.process = cast(subprocess.Popen[str], FakeLiveProcess())
    stream.last_update = 0

    def restart() -> None:
        nonlocal restarted
        restarted = True

    monkeypatch.setattr(stream, 'restart', restart)
    monkeypatch.setattr(device_poller.time, 'monotonic', lambda: 10)

    assert stream.devices() is None
    assert restarted


def test_query_stream_kills_unresponsive_process() -> None:
    stream = DeviceQueryStream()
    process = FakeUnresponsiveProcess()
    stream.process = cast(subprocess.Popen[str], process)

    stream.stop()

    assert process.killed
    assert process.stdout.closed
    assert stream.process is None
