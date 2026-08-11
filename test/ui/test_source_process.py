import threading
import time
import typing as t
from pathlib import Path

import pytest

from recs.cfg.cfg import Cfg
from recs.cfg.device import InputDevice
from recs.cfg.track import Track
from recs.ui import source_process
from recs.ui.source_process import SourceProcess
from recs.ui.source_recorder import SourceControl, SourceFailure


class FakeConnection:
    closed: bool = False

    def __init__(self) -> None:
        self.sent: list[object] = []

    def close(self) -> None:
        self.closed = True

    def poll(self) -> bool:
        return False

    def send(self, message: object) -> None:
        self.sent.append(message)


class BrokenPollConnection(FakeConnection):
    def poll(self) -> bool:
        raise BrokenPipeError


class FakeSendConnection(FakeConnection):
    def __init__(self) -> None:
        super().__init__()
        self.sent_event = threading.Event()

    def send(self, message: object) -> None:
        super().send(message)
        self.sent_event.set()


class FakeEvent:
    _is_set: bool = False

    def is_set(self) -> bool:
        return self._is_set

    def set(self) -> None:
        self._is_set = True


class BlockingSendConnection(FakeConnection):
    def __init__(self) -> None:
        super().__init__()
        self.started = threading.Event()
        self.release = threading.Event()

    def send(self, message: object) -> None:
        self.started.set()
        self.release.wait()
        super().send(message)


class FakeProcess:
    instances: list['FakeProcess'] = []

    def __init__(
        self,
        target: t.Any,
        kwargs: dict[str, t.Any],
        name: str | None = None,
    ) -> None:
        self.alive = False
        self.kwargs = kwargs
        self.name = name
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

    def pipe(*, duplex: bool = True) -> tuple[FakeConnection, FakeConnection]:
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


def test_source_process_starts_recorder_with_gui_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def pipe(*, duplex: bool = True) -> tuple[FakeConnection, FakeConnection]:
        return FakeConnection(), FakeConnection()

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
    owner = SourceProcess(Cfg(gui=True), [Track(source, '1')])

    owner.start()

    recorder_cfg = owner.process.kwargs['cfg']
    assert recorder_cfg.console.gui is False
    assert owner.cfg.console.gui is True


def test_source_process_names_recorder_child(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def pipe(*, duplex: bool = True) -> tuple[FakeConnection, FakeConnection]:
        return FakeConnection(), FakeConnection()

    monkeypatch.setattr(source_process.mp, 'Event', FakeEvent)
    monkeypatch.setattr(source_process.mp, 'Pipe', pipe)
    monkeypatch.setattr(source_process.mp, 'Process', FakeProcess)

    source = InputDevice(
        {
            'default_samplerate': 48_000,
            'max_input_channels': 1,
            'name': 'Mic 1',
        }
    )
    owner = SourceProcess(Cfg(), [Track(source, '1')])

    owner.start()

    assert owner.process.name == 'recs-src-Mic-1'
    assert owner.process.kwargs['process_name'] == 'recs-src-Mic-1'


def test_source_process_applies_device_profile(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    def pipe(*, duplex: bool = True) -> tuple[FakeConnection, FakeConnection]:
        return FakeConnection(), FakeConnection()

    profiles = tmp_path / 'profiles.json'
    profiles.write_text('{"Mic": {"noise_floor": 42}}')
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
    owner = SourceProcess(Cfg(profiles=profiles), [Track(source, '1')])

    owner.start()

    recorder_cfg = owner.process.kwargs['cfg']
    assert recorder_cfg.recording.noise_floor == 42


def test_source_process_updates_track_names(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parent = FakeSendConnection()
    calls = 0

    def pipe(*, duplex: bool = True) -> tuple[FakeConnection, FakeSendConnection]:
        nonlocal calls
        calls += 1
        return (FakeConnection(), parent) if calls == 2 else (FakeConnection(), parent)

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
    track_names = {'Mic': {'Lead Vocal': 1}}
    owner = SourceProcess(Cfg(), [Track(source, '1')], track_names=track_names)

    owner.start()
    owner.set_track_names({'Mic': {'Guitar': 1}})

    assert owner.process.kwargs['track_names'] == track_names
    assert parent.sent_event.wait(0.1)
    assert parent.sent == [SourceControl(track_names={'Mic': {'Guitar': 1}})]


def test_source_controls_do_not_block_recorder_loop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parent = BlockingSendConnection()
    calls = 0

    def pipe(*, duplex: bool = True) -> tuple[FakeConnection, FakeConnection]:
        nonlocal calls
        calls += 1
        if calls == 2:
            return FakeConnection(), parent
        return FakeConnection(), FakeConnection()

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

    start = time.monotonic()
    owner.set_track_names({'Mic': {'Guitar': 1}})

    assert time.monotonic() - start < 0.1
    assert parent.started.wait(0.1)
    parent.release.set()
    owner.stop()
    owner.join()


def test_source_process_uses_per_device_noise_floor(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    def pipe(*, duplex: bool = True) -> tuple[FakeConnection, FakeConnection]:
        return FakeConnection(), FakeConnection()

    profiles = tmp_path / 'profiles.json'
    profiles.write_text(
        '{"Mic": {"noise_floor": 42}, "Ext": {"recording": {"noise_floor": 68}}}'
    )
    monkeypatch.setattr(source_process.mp, 'Event', FakeEvent)
    monkeypatch.setattr(source_process.mp, 'Pipe', pipe)
    monkeypatch.setattr(source_process.mp, 'Process', FakeProcess)

    mic = InputDevice(
        {
            'default_samplerate': 48_000,
            'max_input_channels': 1,
            'name': 'Mic',
        }
    )
    ext = InputDevice(
        {
            'default_samplerate': 48_000,
            'max_input_channels': 1,
            'name': 'Ext',
        }
    )

    SourceProcess(Cfg(noise_floor=80, profiles=profiles), [Track(mic, '1')]).start()
    SourceProcess(Cfg(noise_floor=80, profiles=profiles), [Track(ext, '1')]).start()

    first, second = FakeProcess.instances[-2:]
    assert first.kwargs['cfg'].recording.noise_floor == 42
    assert second.kwargs['cfg'].recording.noise_floor == 68


def test_source_process_ignores_broken_connection_poll(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def pipe(*, duplex: bool = True) -> tuple[FakeConnection, FakeConnection]:
        return BrokenPollConnection(), FakeConnection()

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
    owner.stop()
    owner.join()

    assert owner.stopped


def test_source_process_reports_recorder_start_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail(**kwargs: object) -> None:
        raise ValueError('no input device')

    monkeypatch.setattr(source_process.source_recorder, 'SourceRecorder', fail)
    source = InputDevice(
        {
            'default_samplerate': 48_000,
            'max_input_channels': 1,
            'name': 'Mic',
        }
    )
    connection = FakeSendConnection()

    source_process._run_source_recorder(
        cfg=Cfg(),
        control_connection=FakeConnection(),
        stop_event=FakeEvent(),
        tracks=[Track(source, '1')],
        update_connection=connection,
    )

    assert connection.sent == [
        SourceFailure(message='ValueError: no input device', source_name='Mic')
    ]
