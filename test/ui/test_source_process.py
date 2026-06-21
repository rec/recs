import typing as t

import pytest

from recs.cfg import Cfg, InputDevice, Track
from recs.ui import source_process
from recs.ui.source_process import SourceProcess


class FakeConnection:
    closed: bool = False

    def close(self) -> None:
        self.closed = True

    def poll(self) -> bool:
        return False


class FakeEvent:
    _is_set: bool = False

    def is_set(self) -> bool:
        return self._is_set

    def set(self) -> None:
        self._is_set = True


class FakeProcess:
    instances: list['FakeProcess'] = []

    def __init__(self, target: t.Any, kwargs: dict[str, t.Any]) -> None:
        self.alive = False
        self.kwargs = kwargs
        self.terminated = False
        self.instances.append(self)

    def is_alive(self) -> bool:
        return self.alive

    def join(self, timeout: float | None = None) -> None:
        if self.kwargs['stop_event'].is_set():
            self.alive = False

    def start(self) -> None:
        self.alive = True

    def terminate(self) -> None:
        self.alive = False
        self.terminated = True


def test_source_process_can_be_replaced(monkeypatch: pytest.MonkeyPatch) -> None:
    connections: list[FakeConnection] = []

    def pipe() -> tuple[FakeConnection, FakeConnection]:
        parent = FakeConnection()
        connections.append(parent)
        return parent, FakeConnection()

    monkeypatch.setattr(source_process.mp, 'Event', FakeEvent)
    monkeypatch.setattr(source_process.mp, 'Pipe', pipe)
    monkeypatch.setattr(source_process.mp, 'Process', FakeProcess)

    source = InputDevice(
        {
            'default_samplerate': 48_000,
            'max_input_channels': 1,
            'name': 'Mic',
        }
    )
    owner = SourceProcess(Cfg(), [Track(source, '1')])

    owner.start()
    first = owner.process
    owner.stop()
    owner.join()
    owner.start()

    assert owner.process is not first
    assert first.kwargs['stop_event'].is_set()
    assert connections[0].closed
    assert owner.is_alive
