import multiprocessing as mp
import threading
import time
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import soundfile

from recs.cfg.cfg import Cfg
from recs.cfg.device import InputDevice
from recs.cfg.file_source import FileSource
from recs.cfg.track import Track
from recs.ui import source_process
from recs.ui.source_process import SourceProcess
from recs.ui.source_recorder import SourceControl, SourceFailure, SourceUpdate


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
        target: Any,
        kwargs: dict[str, Any],
        name: str | None = None,
    ) -> None:
        self.alive = False
        self.kwargs = kwargs
        self.name = name
        self.terminated = False
        self.exitcode = 0
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
        self.exitcode = -15


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
    owner = SourceProcess(Cfg(), [Track(source, '1')], Path('session'))

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
    owner = SourceProcess(Cfg(gui=True), [Track(source, '1')], Path('session'))

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
    owner = SourceProcess(Cfg(), [Track(source, '1')], Path('session'))

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
    owner = SourceProcess(Cfg(profiles=profiles), [Track(source, '1')], Path('session'))

    owner.start()

    recorder_cfg = owner.process.kwargs['cfg']
    assert recorder_cfg.recording.noise_floor == 42


def test_source_process_updates_track_names(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parent = FakeSendConnection()

    def pipe(*, duplex: bool = True) -> tuple[FakeConnection, FakeSendConnection]:
        return FakeConnection(), parent

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
    owner = SourceProcess(
        Cfg(), [Track(source, '1')], Path('session'), track_names=track_names
    )

    owner.start()
    owner.set_track_names({'Mic': {'Guitar': 1}})

    assert owner.process.kwargs['track_names'] == track_names
    assert parent.sent_event.wait(0.1)
    assert parent.sent == [SourceControl(track_names={'Mic': {'Guitar': 1}})]


def test_source_process_updates_session_directory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parent = FakeSendConnection()

    def pipe(*, duplex: bool = True) -> tuple[FakeConnection, FakeSendConnection]:
        return FakeConnection(), parent

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
    owner = SourceProcess(Cfg(), [Track(source, '1')], Path('session'))

    owner.start()
    owner.set_session_directory(Path('session-2'))

    assert parent.sent_event.wait(0.1)
    assert parent.sent == [SourceControl(session_directory=Path('session-2'))]


def test_source_process_requests_calibration(
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
    owner = SourceProcess(Cfg(), [Track(source, '1')], Path('session'))

    owner.start()
    owner.calibrate(['1'])

    assert parent.sent_event.wait(0.1)
    assert parent.sent == [SourceControl(calibration_tracks=['1'])]


def test_source_process_enables_live_waveforms(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parent = FakeSendConnection()

    def pipe(*, duplex: bool = True) -> tuple[FakeConnection, FakeSendConnection]:
        return FakeConnection(), parent

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
    owner = SourceProcess(Cfg(), [Track(source, '1')], Path('session'))

    owner.start()
    owner.set_waveforms_enabled(True)

    assert parent.sent_event.wait(0.1)
    assert parent.sent == [SourceControl(waveforms_enabled=True)]


def test_source_process_suspends_writing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parent = FakeSendConnection()

    def pipe(*, duplex: bool = True) -> tuple[FakeConnection, FakeSendConnection]:
        return FakeConnection(), parent

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
    owner = SourceProcess(Cfg(), [Track(source, '1')], Path('session'))

    owner.start()
    owner.set_writing_enabled(False)

    assert parent.sent_event.wait(0.1)
    assert parent.sent == [SourceControl(writing_enabled=False)]


def test_source_process_changes_waveform_generation_after_restart(
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
    owner = SourceProcess(Cfg(), [Track(source, '1')], Path('session'))
    owner.set_waveforms_enabled(True)

    owner.start()
    first_generation = owner.process.kwargs['waveform_generation']
    owner.stop()
    owner.join()
    owner.start()

    assert first_generation == 1
    assert owner.process.kwargs['waveform_generation'] == 2


def test_source_process_updates_tracks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parent = FakeSendConnection()

    def pipe(*, duplex: bool = True) -> tuple[FakeConnection, FakeSendConnection]:
        return FakeConnection(), parent

    monkeypatch.setattr(source_process.mp, 'Event', FakeEvent)
    monkeypatch.setattr(source_process.mp, 'Pipe', pipe)
    monkeypatch.setattr(source_process.mp, 'Process', FakeProcess)
    source = InputDevice(
        {
            'default_samplerate': 48_000,
            'max_input_channels': 2,
            'name': 'Mic',
        }
    )
    owner = SourceProcess(Cfg(), [Track(source, '1-2')], Path('session'))
    tracks = [Track(source, '1'), Track(source, '2')]

    owner.start()
    owner.set_tracks(tracks, {'Mic': {'VL': 1}})

    assert parent.sent_event.wait(0.1)
    assert parent.sent == [SourceControl(track_names={'Mic': {'VL': 1}}, tracks=tracks)]


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
    owner = SourceProcess(Cfg(), [Track(source, '1')], Path('session'))
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

    SourceProcess(
        Cfg(noise_floor=80, profiles=profiles), [Track(mic, '1')], Path('session')
    ).start()
    SourceProcess(
        Cfg(noise_floor=80, profiles=profiles), [Track(ext, '1')], Path('session')
    ).start()

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
    owner = SourceProcess(Cfg(), [Track(source, '1')], Path('session'))

    owner.start()
    owner.stop()
    owner.join()

    assert owner.stopped


def test_source_process_join_drains_real_child_final_updates(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(source_process, 'mp', mp.get_context('fork'))
    input_path = tmp_path / 'input.wav'
    output_path = tmp_path / 'output'
    audio = np.resize(np.array([-0.5, 0.5], dtype=np.float32), (48_000, 1))
    soundfile.write(input_path, audio, 48_000)
    source = FileSource(input_path)
    owner = SourceProcess(
        Cfg(
            output_directory=str(output_path),
            noise_floor=20,
            quiet_after_end=0,
            quiet_before_start=0,
            shortest_file_time=0,
            silent=True,
            stop_after_quiet=0,
        ),
        [Track(source, '1')],
        output_path,
    )

    owner.start()
    deadline = time.monotonic() + 5
    while owner.is_alive and time.monotonic() < deadline:
        time.sleep(0.01)
    owner.join()
    updates = [
        update for update in owner.take_updates() if isinstance(update, SourceUpdate)
    ]

    assert updates
    assert any(update.file_records for update in updates)
    assert any(update.file_end_frames for update in updates)
    assert any(path.exists() for update in updates for path in update.files)


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
        session_directory=Path('session'),
        stop_event=FakeEvent(),
        tracks=[Track(source, '1')],
        update_connection=connection,
    )

    assert connection.sent == [
        SourceFailure(
            message='ValueError: no input device',
            source_name='Mic',
            exception_type='ValueError',
            stop_kind='crash',
        )
    ]


def test_source_process_reports_forced_termination(
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
    owner = SourceProcess(Cfg(), [Track(source, '1')], Path('session'))

    owner.start()
    owner.join()
    failures = [
        update for update in owner.take_updates() if isinstance(update, SourceFailure)
    ]

    assert failures == [
        SourceFailure(
            message='Mic source process forced_termination',
            source_name='Mic',
            exitcode=-15,
            stop_kind='forced_termination',
        )
    ]
