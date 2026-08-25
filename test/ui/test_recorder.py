import json
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from datetime import datetime
from pathlib import Path
from test.conftest import DEVICES, DEVICES_FILE
from typing import Any, NamedTuple

import pytest
from reccy import rpc
from threa import Runnable

from recs.base.errors import ErrorRecord, RecsError
from recs.base.state import ChannelState
from recs.cfg import device, settings
from recs.cfg.cfg import Cfg
from recs.cfg.track import Track
from recs.daemon import external_ipc, gui_ipc, gui_protocol
from recs.ui import (
    disk_space_controller,
    recorder,
    recording_paths,
    recording_track_config,
    session_manifest,
)
from recs.ui.key_events import KeyEvent
from recs.ui.recorder import Recorder
from recs.ui.source_recorder import BufferStats, SourceFailure, SourceFile, SourceUpdate


class DiskUsage(NamedTuple):
    total: int
    used: int
    free: int


class FakePoller(Runnable):
    def __init__(self, interval: float) -> None:
        self.snapshots: list[dict[str, Any] | None] = []

    def latest(self) -> dict[str, Any] | None:
        return self.snapshots.pop(0) if self.snapshots else None

    def poll(self) -> None:
        pass


@pytest.fixture(autouse=True)
def use_temporary_working_directory(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text().splitlines()]


def manifest_path(rec: Recorder) -> Path:
    return rec.session_directory / 'audio/audio-manifest.jsonl'


class FakeConnection:
    def __init__(self) -> None:
        self.messages: list[SourceUpdate] = []

    def poll(self) -> bool:
        return bool(self.messages)

    def recv(self) -> SourceUpdate:
        return self.messages.pop(0)


class FakeSourceProcess:
    def __init__(
        self,
        cfg: Cfg,
        tracks: Sequence[Track],
        session_directory: Path,
        track_names: dict[str, dict[str, int]] | None = None,
    ) -> None:
        self.name = tracks[0].source.name
        self.source = tracks[0].source
        self.tracks = tracks
        self.connection = FakeConnection()
        self.started = False
        self.running = False
        self.alive = False
        self.start_count = 0
        self.track_names = track_names or {}
        self.cfg = cfg
        self.session_directory = session_directory
        self.pending_updates: list[SourceUpdate] = []

    @property
    def is_alive(self) -> bool:
        return self.started and self.alive

    @property
    def required_channels(self) -> int:
        return self.source.channels

    def join(self, timeout: float | None = None) -> None:
        self.alive = False
        self.started = False

    def start(self) -> None:
        self.started = True
        self.running = True
        self.alive = True
        self.start_count += 1

    def stop(self) -> None:
        self.running = False
        self.alive = False

    def set_track_names(self, track_names: dict[str, dict[str, int]]) -> None:
        self.track_names = track_names

    def set_cfg(self, cfg: Cfg, revision: int | None = None) -> None:
        self.cfg = cfg
        self.cfg_revision = revision

    def set_session_directory(self, session_directory: Path) -> None:
        self.session_directory = session_directory

    def calibrate(self, tracks: list[str]) -> None:
        self.connection.messages.append(
            SourceUpdate(
                channels={},
                files=[],
                frames=0,
                source_name=self.name,
                calibration=dict.fromkeys(tracks, 6.0),
            )
        )

    def set_tracks(
        self, tracks: list[Track], track_names: dict[str, dict[str, int]]
    ) -> None:
        self.tracks = tracks
        self.track_names = track_names

    def take_updates(self) -> list[SourceUpdate]:
        updates, self.pending_updates = self.pending_updates, []
        return updates


class ClosedDisplay(Runnable):
    enabled = True
    closed = True

    def __init__(
        self,
        rows: Callable[[], Iterator[Mapping[str, object]]],
        cfg: Cfg,
        *,
        errors: Callable[[], Iterable[str]] | None = None,
    ) -> None:
        self.rows = rows
        self.cfg = cfg
        self.errors = errors or tuple
        super().__init__()

    def update(self) -> None:
        pass

    def take_key_events(self) -> list[KeyEvent]:
        return []


class FakeKeyRecorder:
    def __init__(self, events: list[KeyEvent]) -> None:
        self.events = events

    def take_events(self) -> list[KeyEvent]:
        events, self.events = self.events, []
        return events

    def start(self) -> None:
        pass

    def stop(self) -> None:
        pass


class FakeControlDisplay:
    closed = False

    def __init__(self, requests: list['FakeControlRequest']) -> None:
        self.requests = requests

    def take_key_events(self) -> list[KeyEvent]:
        return []

    def take_control_requests(self) -> list['FakeControlRequest']:
        requests, self.requests = self.requests, []
        return requests


class FakeControlRequest:
    def __init__(self, request: gui_protocol.Request | None = None) -> None:
        self.request = request or gui_protocol.Calibrate(type='calibrate')
        self.responses: list[gui_protocol.Response] = []

    def respond(self, response: gui_protocol.Response) -> None:
        self.responses.append(response)


def test_recorder_reports_no_selected_channels(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    mock_devices: None,
) -> None:
    monkeypatch.setattr(recorder, 'DevicePoller', FakePoller)
    monkeypatch.setattr(recorder, 'SourceProcess', FakeSourceProcess)

    rec = Recorder(Cfg(include=['e'], exclude=['e'], silent=True))

    assert rec.error_records()[0].message == 'No channels selected'
    assert rec.error_records()[0].timestamp.endswith('Z')
    assert rec.error_messages() == ['No channels selected']
    assert caplog.messages == ['No channels selected']


def test_recorder_runs_without_devices(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setattr(device, 'query_devices', lambda: [])
    monkeypatch.setattr(recorder, 'DevicePoller', FakePoller)
    monkeypatch.setattr(recorder, 'SourceProcess', FakeSourceProcess)

    rec = Recorder(Cfg(silent=True))

    assert rec._devices.hardware == {}
    assert rec._devices.poller is not None
    assert rec.error_records()[0].message == 'No input devices detected'
    assert rec.error_records()[0].timestamp.endswith('Z')
    assert rec.error_messages() == ['No input devices detected']
    assert caplog.messages == ['No input devices detected']


def test_recorder_adds_device_detected_after_start(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(device, 'query_devices', lambda: [])
    monkeypatch.setattr(recorder, 'DevicePoller', FakePoller)
    monkeypatch.setattr(recorder, 'SourceProcess', FakeSourceProcess)
    rec = Recorder(Cfg(include=['Mic'], silent=True))
    mic_info = next(info for info in DEVICES if info['name'] == 'Mic')
    assert rec._devices.poller is not None
    assert rec.error_messages() == []
    rec._devices.poller.snapshots = [{'Mic': mic_info}]
    rec._poll_devices()

    assert 'Mic' in rec._devices.hardware
    assert rec._devices.hardware['Mic'].started
    assert list(rec.state.state) == ['Mic']


def test_recorder_replaces_returning_device(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setattr(recorder, 'DevicePoller', FakePoller)
    monkeypatch.setattr(recorder, 'SourceProcess', FakeSourceProcess)
    rec = Recorder(Cfg(devices=Path(DEVICES_FILE), silent=True))
    mic_info = next(info for info in DEVICES if info['name'] == 'Mic')
    mic = rec._devices.hardware['Mic']

    rec._devices.poller.snapshots = [
        {},
        {'Mic': mic_info, 'Unexpected': mic_info},
        {},
        {'Mic': mic_info},
    ]

    rec._poll_devices()
    assert not any(source.started for source in rec._devices.hardware.values())

    rec._poll_devices()
    assert mic.started
    assert mic.start_count == 1
    assert not any(
        source.started
        for name, source in rec._devices.hardware.items()
        if name != 'Mic'
    )

    rec._poll_devices()
    rec._reap_sources()
    assert not mic.started
    assert any(
        warning.message == 'Device Mic went offline' for warning in rec.error_records()
    )
    assert 'Device Mic went offline' in caplog.messages

    rec._poll_devices()
    assert mic.started
    assert mic.start_count == 2


def test_recorder_loop_runs_without_live_display(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    polled = False
    monkeypatch.setattr(recorder, 'DevicePoller', FakePoller)
    monkeypatch.setattr(recorder, 'SourceProcess', FakeSourceProcess)
    rec = Recorder(Cfg(devices=Path(DEVICES_FILE), silent=True))

    def poll_devices() -> None:
        nonlocal polled
        polled = True
        rec.stop()

    monkeypatch.setattr(rec, '_poll_devices', poll_devices)

    rec._run()

    assert polled


def test_recorder_loop_polls_midi(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    midi_recorders: list[Any] = []

    class FakeMidiRecorder(Runnable):
        def __init__(self, *args: object, **kwargs: object) -> None:
            self.poll_count = 0
            midi_recorders.append(self)
            super().__init__()

        def poll(self) -> None:
            self.poll_count += 1

        def status(self) -> list[dict[str, object]]:
            return [
                {
                    'name': 'Launchkey',
                    'open': bool(self.running),
                    'failed': False,
                    'message_count': self.poll_count,
                    'last_message_timestamp': None,
                }
            ]

    monkeypatch.setattr(recorder, 'DevicePoller', FakePoller)
    monkeypatch.setattr(recorder, 'SourceProcess', FakeSourceProcess)
    monkeypatch.setattr(recorder, 'MidiRecorder', FakeMidiRecorder)
    rec = Recorder(Cfg(devices=Path(DEVICES_FILE), silent=True))

    def poll_devices() -> None:
        rec.stop()

    monkeypatch.setattr(rec, '_poll_devices', poll_devices)

    rec._run()

    assert midi_recorders[0].poll_count == 1
    assert rec._control.status_snapshot().midi == [
        {
            'name': 'Launchkey',
            'open': False,
            'failed': False,
            'message_count': 1,
            'last_message_timestamp': None,
        }
    ]


def test_recorder_stops_when_gui_display_closes(
    monkeypatch: pytest.MonkeyPatch,
    mock_devices: None,
    mock_mp: None,
) -> None:
    monkeypatch.setattr(recorder, 'SourceProcess', FakeSourceProcess)
    monkeypatch.setattr(recorder.gui_process, 'GuiProcess', ClosedDisplay)
    rec = Recorder(Cfg(gui=True))

    rec._run()

    assert rec.stopped


def test_display_receives_recorder_errors(
    monkeypatch: pytest.MonkeyPatch,
    mock_devices: None,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setattr(recorder, 'DevicePoller', FakePoller)
    monkeypatch.setattr(recorder, 'SourceProcess', FakeSourceProcess)
    monkeypatch.setattr(recorder.live, 'Live', ClosedDisplay)
    rec = Recorder(Cfg(devices=Path(DEVICES_FILE)))
    flower = rec._devices.hardware['Flower 8']
    rec._devices.poller.snapshots = [
        {'Flower 8': {'max_input_channels': 2, 'name': 'Flower 8'}}
    ]

    rec._poll_devices()

    assert rec.live is not None
    assert rec.live.errors() == ['Flower 8 has 2 input channels; 10 required']
    assert caplog.messages == ['Flower 8 has 2 input channels; 10 required']
    assert not flower.started


def test_gui_starts_sources_before_display_process(
    monkeypatch: pytest.MonkeyPatch,
    mock_devices: None,
) -> None:
    rec: Recorder

    class OrderDisplay(ClosedDisplay):
        def start(self) -> None:
            assert any(source.started for source in rec._devices.hardware.values())
            super().start()

    monkeypatch.setattr(recorder, 'SourceProcess', FakeSourceProcess)
    monkeypatch.setattr(recorder.gui_process, 'GuiProcess', OrderDisplay)
    rec = Recorder(Cfg(gui=True))

    rec._run()


def test_daemon_mode_uses_gui_server_instead_of_local_gui(
    monkeypatch: pytest.MonkeyPatch,
    mock_devices: None,
) -> None:
    class DaemonDisplay(ClosedDisplay):
        pass

    monkeypatch.setenv('RECS_DAEMON', '1')
    monkeypatch.setattr(recorder, 'SourceProcess', FakeSourceProcess)
    monkeypatch.setattr(recorder.gui_process, 'GuiProcess', pytest.fail)
    monkeypatch.setattr(recorder.gui_ipc, 'DaemonGuiServer', DaemonDisplay)

    rec = Recorder(Cfg(gui=True))

    assert isinstance(rec.live, DaemonDisplay)


def test_external_ipc_start_failure_keeps_recorder_usable(
    monkeypatch: pytest.MonkeyPatch,
    mock_devices: None,
) -> None:
    class BrokenExternal:
        def __init__(self) -> None:
            self.closed = False

        def start(self) -> None:
            raise OSError('address in use')

        def close(self) -> None:
            self.closed = True

    monkeypatch.setenv('RECS_DAEMON', '1')
    monkeypatch.setattr(recorder, 'SourceProcess', FakeSourceProcess)
    monkeypatch.setattr(recorder.Runnables, 'start', lambda self: None)
    monkeypatch.setattr(recorder.Runnable, 'start', lambda self: None)
    rec = Recorder(Cfg(silent=True))
    external = BrokenExternal()
    rec.external = external

    rec.start()

    assert external.closed
    assert rec.external is None
    assert rec.error_messages() == ['Cannot start external IPC server: address in use']
    assert isinstance(rec.live, gui_ipc.DaemonGuiServer)
    assert rec.live.external_ipc_error == 'address in use'


def test_external_control_requests_use_recorder_handler(
    monkeypatch: pytest.MonkeyPatch,
    mock_devices: None,
) -> None:
    class External:
        def __init__(self) -> None:
            self.requests = [
                external_ipc.ControlRequest(rpc.Request(command='mutable_attributes'))
            ]
            self.responses: list[rpc.Result] = []

        def take_requests(self) -> list[external_ipc.ControlRequest]:
            return self.requests

        def respond(
            self, request: external_ipc.ControlRequest, response: rpc.Result
        ) -> None:
            self.responses.append(response)

    monkeypatch.setattr(recorder, 'SourceProcess', FakeSourceProcess)
    rec = Recorder(Cfg(silent=True))
    external = External()
    rec.external = external

    rec._receive_control_requests()

    assert external.responses == [
        {
            'type': 'mutable_attributes_result',
            'mutable_attributes': sorted(rec.cfg.mutable_attributes),
        }
    ]


def test_external_shutdown_only_stops_recorder_once(
    monkeypatch: pytest.MonkeyPatch,
    mock_devices: None,
) -> None:
    class External:
        def __init__(self) -> None:
            self.requests = [
                external_ipc.ControlRequest(rpc.Request(command='shutdown'))
                for value in ['request-1', 'request-2']
            ]
            self.responses: list[rpc.Result] = []

        def take_requests(self) -> list[external_ipc.ControlRequest]:
            return self.requests

        def respond(
            self, request: external_ipc.ControlRequest, response: rpc.Result
        ) -> None:
            self.responses.append(response)

    calls: list[str] = []
    monkeypatch.setattr(recorder, 'SourceProcess', FakeSourceProcess)
    rec = Recorder(Cfg(silent=True))
    external = External()
    rec.external = external
    monkeypatch.setattr(rec, 'stop', lambda: calls.append('stop'))

    rec._receive_control_requests()

    assert calls == ['stop']
    assert external.responses == [
        'ok',
        'ok',
    ]


def test_failed_device_waits_for_reconnect(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(recorder, 'DevicePoller', FakePoller)
    monkeypatch.setattr(recorder, 'SourceProcess', FakeSourceProcess)
    rec = Recorder(Cfg(devices=Path(DEVICES_FILE), silent=True))
    mic_info = next(info for info in DEVICES if info['name'] == 'Mic')
    mic = rec._devices.hardware['Mic']
    rec._devices.poller.snapshots = [
        {'Mic': mic_info},
        {'Mic': mic_info},
        {},
        {'Mic': mic_info},
    ]

    rec._poll_devices()
    mic.alive = False
    rec._reap_sources()
    rec._poll_devices()

    assert not mic.started
    assert mic.start_count == 1

    rec._poll_devices()
    rec._poll_devices()

    assert mic.started
    assert mic.start_count == 2


def test_device_with_too_few_channels_stays_offline(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setattr(recorder, 'DevicePoller', FakePoller)
    monkeypatch.setattr(recorder, 'SourceProcess', FakeSourceProcess)
    rec = Recorder(Cfg(devices=Path(DEVICES_FILE), silent=True))
    flower = rec._devices.hardware['Flower 8']
    rec._devices.poller.snapshots = [
        {'Flower 8': {'max_input_channels': 2, 'name': 'Flower 8'}}
    ]

    rec._poll_devices()

    assert not flower.started
    assert caplog.messages == ['Flower 8 has 2 input channels; 10 required']


def test_slow_device_clock_stays_offline(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    now = 100.0
    monkeypatch.setattr(recorder.times, 'timestamp', lambda: now)
    monkeypatch.setattr(recorder, 'DevicePoller', FakePoller)
    monkeypatch.setattr(recorder, 'SourceProcess', FakeSourceProcess)
    rec = Recorder(Cfg(devices=Path(DEVICES_FILE), include=['Mic'], silent=True))
    mic_info = next(info for info in DEVICES if info['name'] == 'Mic')
    mic = rec._devices.hardware['Mic']
    rec._devices.poller.snapshots = [{'Mic': mic_info}]

    rec._poll_devices()
    now = 110.0
    rec._receive_update(
        SourceUpdate(
            channels={'1': ChannelState()},
            files=[],
            frames=48_000,
            source_name='Mic',
        )
    )

    assert not mic.running
    assert 'Mic' in rec._devices.failed
    assert caplog.messages == ['Device Mic lagging behind real time']


def test_slow_device_clock_reports_once_per_session(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    now = 100.0
    monkeypatch.setattr(recorder.times, 'timestamp', lambda: now)
    monkeypatch.setattr(recorder, 'DevicePoller', FakePoller)
    monkeypatch.setattr(recorder, 'SourceProcess', FakeSourceProcess)
    rec = Recorder(Cfg(devices=Path(DEVICES_FILE), include=['Mic'], silent=True))
    mic_info = next(info for info in DEVICES if info['name'] == 'Mic')
    mic = rec._devices.hardware['Mic']
    rec._devices.poller.snapshots = [{'Mic': mic_info}]
    update = SourceUpdate(
        channels={'1': ChannelState()},
        files=[],
        frames=48_000,
        source_name='Mic',
    )

    rec._poll_devices()
    now = 110.0
    rec._receive_update(update)
    mic.running = True
    rec._receive_update(update)

    assert caplog.messages == ['Device Mic lagging behind real time']


def test_slow_device_clock_ignores_startup_grace(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    now = 100.0
    monkeypatch.setattr(recorder.times, 'timestamp', lambda: now)
    monkeypatch.setattr(recorder, 'DevicePoller', FakePoller)
    monkeypatch.setattr(recorder, 'SourceProcess', FakeSourceProcess)
    rec = Recorder(Cfg(devices=Path(DEVICES_FILE), include=['Mic'], silent=True))
    mic_info = next(info for info in DEVICES if info['name'] == 'Mic')
    mic = rec._devices.hardware['Mic']
    rec._devices.poller.snapshots = [{'Mic': mic_info}]

    rec._poll_devices()
    now = 104.0
    rec._receive_update(
        SourceUpdate(
            channels={'1': ChannelState()},
            files=[],
            frames=1,
            source_name='Mic',
        )
    )

    assert mic.running
    assert 'Mic' not in rec._devices.failed
    assert caplog.messages == []


def test_stalled_source_is_stopped(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    now = 100.0
    monkeypatch.setattr(recorder.times, 'timestamp', lambda: now)
    monkeypatch.setattr(recorder, 'DevicePoller', FakePoller)
    monkeypatch.setattr(recorder, 'SourceProcess', FakeSourceProcess)
    rec = Recorder(Cfg(devices=Path(DEVICES_FILE), include=['Mic'], silent=True))
    mic_info = next(info for info in DEVICES if info['name'] == 'Mic')
    mic = rec._devices.hardware['Mic']
    rec._devices.poller.snapshots = [{'Mic': mic_info}]

    rec._poll_devices()
    now += recorder.SOURCE_STALL_TIMEOUT + 1
    rec._stop_stalled_sources()

    assert not mic.started
    assert 'Mic' in rec._devices.failed
    assert rec.error_records() == [
        ErrorRecord(
            timestamp='1970-01-01T00:01:51.000Z',
            message='Device Mic stopped sending updates',
        )
    ]
    assert caplog.messages == ['Device Mic stopped sending updates']


def test_source_failure_is_reported(
    monkeypatch: pytest.MonkeyPatch,
    mock_devices: None,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setattr(recorder, 'SourceProcess', FakeSourceProcess)
    rec = Recorder(Cfg(devices=Path(DEVICES_FILE), include=['Mic'], silent=True))

    rec._receive_source_message(
        SourceFailure(message='ValueError: no input device', source_name='Mic')
    )

    assert rec.error_records()[0].message == (
        'Device Mic failed: ValueError: no input device'
    )
    assert 'Mic' in rec._devices.failed
    assert caplog.messages == ['Device Mic failed: ValueError: no input device']


def test_recorder_finishes_with_all_devices_offline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(recorder, 'DevicePoller', FakePoller)
    monkeypatch.setattr(recorder, 'SourceProcess', FakeSourceProcess)
    rec = Recorder(Cfg(devices=Path(DEVICES_FILE), silent=True, total_run_time=0.1))
    rec.state.start_time -= 1

    assert rec._done([])


def test_recorder_records_buffer_overflow_event(
    monkeypatch: pytest.MonkeyPatch,
    mock_devices: None,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(recorder.times, 'timestamp', lambda: 0.0)
    monkeypatch.setattr(recorder, 'DevicePoller', FakePoller)
    monkeypatch.setattr(recorder, 'SourceProcess', FakeSourceProcess)
    rec = Recorder(Cfg(include=['Mic'], output_directory=str(tmp_path), silent=True))
    rec._start_manifest()

    rec._receive_update(
        SourceUpdate(
            channels={'1': ChannelState()},
            files=[],
            frames=48_000,
            source_name='Mic',
            buffer_stats=BufferStats(
                dropped_blocks=1,
                dropped_frames=512,
                max_queued_seconds=0.5,
                queued_seconds=0.25,
            ),
        )
    )

    records = read_jsonl(manifest_path(rec))
    assert records[1] == {
        'type': 'buffer_overflow',
        'timestamp': '1970-01-01T00:00:00.000Z',
        'dropped_blocks': 1,
        'dropped_frames': 512,
        'source': 'Mic',
        'max_queued_seconds': 0.5,
        'queued_seconds': 0.25,
    }


def test_recorder_checks_for_unfinished_sessions_before_starting_manifest(
    monkeypatch: pytest.MonkeyPatch,
    mock_devices: None,
    tmp_path: Path,
) -> None:
    roots: list[Path] = []
    monkeypatch.setattr(recorder, 'SourceProcess', FakeSourceProcess)
    monkeypatch.setattr(
        recorder.recovery_report, 'report_unfinished_sessions', roots.append
    )
    rec = Recorder(Cfg(include=['Mic'], output_directory=str(tmp_path), silent=True))

    rec._start_manifest()

    assert roots == [tmp_path]


def test_recorder_records_buffer_pressure_before_drops(
    monkeypatch: pytest.MonkeyPatch,
    mock_devices: None,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(recorder.times, 'timestamp', lambda: 0.0)
    monkeypatch.setattr(recorder, 'DevicePoller', FakePoller)
    monkeypatch.setattr(recorder, 'SourceProcess', FakeSourceProcess)
    rec = Recorder(
        Cfg(
            audio_buffer_seconds=1,
            include=['Mic'],
            output_directory=str(tmp_path),
            silent=True,
        )
    )
    rec._start_manifest()

    rec._receive_update(
        SourceUpdate(
            channels={'1': ChannelState()},
            files=[],
            frames=48_000,
            source_name='Mic',
            buffer_stats=BufferStats(max_queued_seconds=0.8, queued_seconds=0.8),
        )
    )

    records = read_jsonl(manifest_path(rec))
    assert records[1]['type'] == 'buffer_pressure'
    assert records[1]['max_queued_seconds'] == 0.8
    assert records[1]['queued_seconds'] == 0.8


def test_recorder_rows_include_buffer_stats(
    monkeypatch: pytest.MonkeyPatch,
    mock_devices: None,
) -> None:
    monkeypatch.setattr(recorder, 'DevicePoller', FakePoller)
    monkeypatch.setattr(recorder, 'SourceProcess', FakeSourceProcess)
    rec = Recorder(Cfg(include=['Mic'], silent=True))
    rec._devices.buffer_stats['Mic'] = BufferStats(
        queued_seconds=0.25, dropped_frames=512
    )

    rows = list(rec.rows())

    assert rows[1]['buffer'] == 0.25
    assert rows[1]['dropped'] == 512


def test_recorder_summarizes_interrupt(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    mock_devices: None,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(recorder, 'DevicePoller', FakePoller)
    monkeypatch.setattr(recorder, 'SourceProcess', FakeSourceProcess)
    monkeypatch.setattr(recorder.times, 'timestamp', lambda: 100.0)
    rec = Recorder(Cfg(silent=True))
    first = tmp_path / 'first.wav'
    second = tmp_path / 'second.wav'
    first.touch()
    second.touch()
    files = (second, tmp_path / 'deleted.wav', first)
    rec.session.files_written.update(files)
    monkeypatch.setattr(recorder.times, 'timestamp', lambda: 165.25)

    def interrupt() -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr(rec, '_run', interrupt)

    rec.run()

    assert capsys.readouterr() == (
        f'Recording time: 1:05.250\nFiles written:\n  {first}\n  {second}\n',
        'Interrupted\n',
    )


def test_recorder_output_folder_prefers_written_files(
    monkeypatch: pytest.MonkeyPatch,
    mock_devices: None,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(recorder, 'DevicePoller', FakePoller)
    monkeypatch.setattr(recorder, 'SourceProcess', FakeSourceProcess)
    rec = Recorder(Cfg(include=['Mic'], output_directory=str(tmp_path), silent=True))
    path = tmp_path / 'session/take.wav'
    path.parent.mkdir()
    path.touch()
    rec.session.files_written.add(path)

    assert rec._output_folder() == path.parent


def test_open_folder_uses_platform_file_manager(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    commands: list[list[str]] = []
    monkeypatch.setattr(recording_paths.sys, 'platform', 'darwin')
    monkeypatch.setattr(
        recording_paths.subprocess,
        'run',
        lambda command, check: commands.append(command),
    )

    recording_paths.open_folder(tmp_path)

    assert commands == [['open', str(tmp_path)]]


def test_live_input_manifest_omits_source(
    monkeypatch: pytest.MonkeyPatch,
    mock_devices: None,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(recorder, 'DevicePoller', FakePoller)
    monkeypatch.setattr(recorder, 'SourceProcess', FakeSourceProcess)
    rec = Recorder(Cfg(include=['Mic'], output_directory=str(tmp_path), silent=True))
    rec._start_manifest()
    path = rec.session_directory / 'audio/mic.wav'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch()

    rec._receive_update(
        SourceUpdate(
            channels={'1': ChannelState()},
            files=[path],
            frames=48_000,
            source_name='Mic',
            file_records=[
                SourceFile(
                    path=path,
                    source_name='Mic',
                    track=1,
                    channels=1,
                    sample_rate=48_000,
                    bit_depth=64,
                )
            ],
        )
    )
    rec._finish_manifest()

    records = read_jsonl(manifest_path(rec))
    for record in records:
        record.pop('timestamp', None)
    assert records[1:3] == [
        {
            'type': 'file_started',
            'kind': 'audio',
            'path': 'mic.wav',
            'track': 1,
            'channels': 1,
            'sample_rate': 48_000,
            'bit_depth': 64,
        },
        {
            'type': 'file_finished',
            'kind': 'audio',
            'path': 'mic.wav',
            'track': 1,
            'channels': 1,
            'sample_rate': 48_000,
            'bit_depth': 64,
        },
    ]


def test_recorder_writes_one_local_manifest_per_medium(
    monkeypatch: pytest.MonkeyPatch,
    mock_devices: None,
    tmp_path: Path,
) -> None:
    nodes = tmp_path / 'osc.toml'
    nodes.write_text('')
    monkeypatch.setattr(recorder, 'DevicePoller', FakePoller)
    monkeypatch.setattr(recorder, 'SourceProcess', FakeSourceProcess)
    rec = Recorder(
        Cfg(
            include=['Mic'],
            output_directory=str(tmp_path),
            osc_nodes=nodes,
            silent=True,
        )
    )
    rec._start_manifest()

    for session, medium, name in (
        (rec.session, 'audio', 'take.wav'),
        (rec.midi_session, 'midi', 'keys.mid'),
        (rec.osc_session, 'osc', 'x18.jsonl'),
    ):
        path = rec.session_directory / medium / name
        path.touch()
        session.write(
            session_manifest.ManifestFile(
                type='file_finished',
                kind=medium,
                timestamp='now',
                path=path.as_posix(),
            )
        )
    rec._finish_manifest()

    for medium, name in (
        ('audio', 'audio-manifest.jsonl'),
        ('midi', 'midi-manifest.jsonl'),
        ('osc', 'osc-manifest.jsonl'),
    ):
        manifest = rec.session_directory / medium / name
        records = read_jsonl(manifest)
        assert [record['path'] for record in records if 'path' in record] == [
            {'audio': 'take.wav', 'midi': 'keys.mid', 'osc': 'x18.jsonl'}[medium]
        ]


def test_manifest_records_source_frame_counts(
    monkeypatch: pytest.MonkeyPatch,
    mock_devices: None,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(recorder, 'DevicePoller', FakePoller)
    monkeypatch.setattr(recorder, 'SourceProcess', FakeSourceProcess)
    rec = Recorder(Cfg(include=['Mic'], output_directory=str(tmp_path), silent=True))
    rec._start_manifest()
    path = rec.session_directory / 'audio/mic.wav'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch()

    rec._receive_update(
        SourceUpdate(
            channels={'1': ChannelState(is_active=True)},
            files=[path],
            frames=512,
            source_name='Mic',
            file_records=[
                SourceFile(
                    path=path,
                    source_name='Mic',
                    track=1,
                    channels=1,
                    sample_rate=48_000,
                    bit_depth=64,
                    start_frame=256,
                )
            ],
            file_end_frames={path: 768},
            frame_count=1024,
        )
    )
    rec._finish_manifest()

    records = read_jsonl(manifest_path(rec))
    for record in records:
        record.pop('timestamp', None)
    assert records[1:4] == [
        {
            'type': 'file_started',
            'kind': 'audio',
            'frame_count': 256,
            'path': 'mic.wav',
            'track': 1,
            'channels': 1,
            'sample_rate': 48_000,
            'bit_depth': 64,
        },
        {
            'type': 'track_started',
            'frame_count': 1024,
            'source': 'Mic',
            'track': '1',
        },
        {
            'type': 'file_finished',
            'kind': 'audio',
            'frame_count': 768,
            'path': 'mic.wav',
            'track': 1,
            'channels': 1,
            'sample_rate': 48_000,
            'bit_depth': 64,
        },
    ]


@pytest.mark.parametrize('field', ['dry_run', 'silence_preview'])
def test_preview_modes_do_not_write_manifest(
    field: str,
    monkeypatch: pytest.MonkeyPatch,
    mock_devices: None,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(recorder, 'DevicePoller', FakePoller)
    monkeypatch.setattr(recorder, 'SourceProcess', FakeSourceProcess)
    rec = Recorder(Cfg(**{field: True}, include=['Mic'], silent=True))

    rec._finish_manifest()

    assert not manifest_path(rec).exists()


def test_silence_preview_report_recommends_thresholds(
    monkeypatch: pytest.MonkeyPatch,
    mock_devices: None,
) -> None:
    monkeypatch.setattr(recorder, 'DevicePoller', FakePoller)
    monkeypatch.setattr(recorder, 'SourceProcess', FakeSourceProcess)
    rec = Recorder(
        Cfg(silence_preview=True, include=['Mic'], preview_headroom=9, silent=True)
    )
    rec.state.update({'Mic': {'1': ChannelState(max_amp=0.5, min_amp=-0.5)}})

    assert rec._silence_preview_report() == {
        'measurements': {'Mic - 1': 6.020599913279624, '(all)': 6.020599913279624},
        'profiles': {'Mic': {'noise_floor': 15.0}},
    }


def test_calibrate_control_request_sets_channel_noise_floor(
    monkeypatch: pytest.MonkeyPatch,
    mock_devices: None,
) -> None:
    monkeypatch.setattr(recorder, 'DevicePoller', FakePoller)
    monkeypatch.setattr(recorder, 'SourceProcess', FakeSourceProcess)
    monkeypatch.setattr(
        recorder.connection,
        'wait',
        lambda c, timeout: [i for i in c if i.poll()],
    )
    rec = Recorder(Cfg(include=['Mic'], preview_headroom=9, silent=True))
    rec._devices.hardware['Mic'].start()
    request = FakeControlRequest()
    rec.live = FakeControlDisplay([request])

    rec._receive_control_requests()

    assert all(source.cfg is rec.cfg for source in rec._devices.sources.values())
    assert rec.cfg.recording.channel_noise_floors == {'Mic': {'1': 15.0}}
    assert request.responses == [
        gui_protocol.Calibrated(
            type='calibrated',
            measurements={'Mic - 1': 6.0},
            noise_floors={'Mic': {'1': 15.0}},
        )
    ]


def test_calibrate_control_request_requires_online_channels(
    monkeypatch: pytest.MonkeyPatch,
    mock_devices: None,
) -> None:
    monkeypatch.setattr(recorder, 'DevicePoller', FakePoller)
    monkeypatch.setattr(recorder, 'SourceProcess', FakeSourceProcess)
    rec = Recorder(Cfg(include=['Mic'], silent=True))
    request = FakeControlRequest()
    rec.live = FakeControlDisplay([request])

    rec._receive_control_requests()

    assert request.responses == [
        gui_protocol.Error(
            type='error', message='No online audio channels to calibrate'
        )
    ]


def test_calibration_selects_both_stereo_channels(
    monkeypatch: pytest.MonkeyPatch,
    mock_devices: None,
) -> None:
    monkeypatch.setattr(recorder, 'DevicePoller', FakePoller)
    monkeypatch.setattr(recorder, 'SourceProcess', FakeSourceProcess)
    rec = Recorder(Cfg(include=['Ext'], silent=True))
    rec._devices.hardware['Ext'].start()

    assert rec._calibration._tracks({'Ext': [1]}) == {'Ext': ['1-2']}


def test_recorder_saves_and_restores_track_settings(
    monkeypatch: pytest.MonkeyPatch,
    mock_devices: None,
    tmp_path: Path,
) -> None:
    path = tmp_path / 'settings.json'
    monkeypatch.setattr(settings, 'settings_path', lambda: path)
    monkeypatch.setattr(recorder, 'DevicePoller', FakePoller)
    monkeypatch.setattr(recorder, 'SourceProcess', FakeSourceProcess)
    rec = Recorder(Cfg(include=['Ext'], save_settings=True, silent=True))
    request = gui_protocol.SetTracks(
        type='set_tracks',
        source='Ext',
        tracks=[
            gui_protocol.ChannelTrack(channels=[1], name='VL'),
            gui_protocol.ChannelTrack(channels=[2]),
        ],
    )

    rec._control.set_tracks(request)
    loaded = settings.load(Cfg(include=['Ext'], save_settings=True, silent=True))
    restored = Recorder(loaded.cfg, loaded)

    assert [track.name for track in restored._devices.sources['Ext'].tracks] == [
        '1',
        '2',
        '3',
    ]
    assert restored._control.track_names == {'Ext': {'VL': 1}}


def test_control_request_saves_output_directory_root(
    monkeypatch: pytest.MonkeyPatch,
    mock_devices: None,
    tmp_path: Path,
) -> None:
    settings_path = tmp_path / 'settings.json'
    output_directory = tmp_path / 'recs' / 'audio'
    monkeypatch.setattr(settings, 'settings_path', lambda: settings_path)
    monkeypatch.setattr(recorder, 'DevicePoller', FakePoller)
    monkeypatch.setattr(recorder, 'SourceProcess', FakeSourceProcess)
    rec = Recorder(Cfg(include=['Mic'], save_settings=True, silent=True))

    rec._control.set_cfg(
        gui_protocol.SetCfg(
            type='set_cfg',
            address='directory.output_directory',
            value=str(output_directory),
        )
    )
    loaded = settings.load(Cfg(include=['Mic'], save_settings=True, silent=True))

    assert rec.cfg.directory.output_directory == str(output_directory)
    assert rec.session_directory.parent == output_directory
    assert loaded.cfg.directory.output_directory == str(output_directory)


def test_track_layout_updates_state_on_next_source_update(
    monkeypatch: pytest.MonkeyPatch,
    mock_devices: None,
) -> None:
    monkeypatch.setattr(recorder, 'DevicePoller', FakePoller)
    monkeypatch.setattr(recorder, 'SourceProcess', FakeSourceProcess)
    rec = Recorder(Cfg(include=['Ext'], silent=True))
    source = rec._devices.sources['Ext']
    rec._control.track_names = {'Ext': {'VL': 1}}
    source.set_tracks(
        [
            Track(source.source, '1'),
            Track(source.source, '2'),
            Track(source.source, '3'),
        ],
        rec._control.track_names,
    )

    rec._receive_update(
        SourceUpdate(
            channels={'1': ChannelState(), '2': ChannelState(), '3': ChannelState()},
            files=[],
            frames=0,
            source_name='Ext',
            track_layout=['1', '2', '3'],
        )
    )

    assert set(rec.state.state['Ext']) == {'1', '2', '3'}
    assert rec.state.track_names['Ext', '1'] == 'VL'


def test_control_request_reports_capabilities(
    monkeypatch: pytest.MonkeyPatch,
    mock_devices: None,
) -> None:
    monkeypatch.setattr(recorder, 'DevicePoller', FakePoller)
    monkeypatch.setattr(recorder, 'SourceProcess', FakeSourceProcess)
    rec = Recorder(Cfg(include=['Mic'], silent=True))
    request = FakeControlRequest(gui_protocol.Capabilities(type='capabilities'))
    rec.live = FakeControlDisplay([request])

    rec._receive_control_requests()

    response = request.responses[0]
    assert isinstance(response, gui_protocol.CapabilitiesResult)
    assert response.version == 4
    assert 'status_snapshot' in response.commands
    assert 'shutdown' in response.commands


def test_control_request_marks_manifest(
    monkeypatch: pytest.MonkeyPatch,
    mock_devices: None,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(recorder, 'DevicePoller', FakePoller)
    monkeypatch.setattr(recorder, 'SourceProcess', FakeSourceProcess)
    rec = Recorder(Cfg(include=['Mic'], output_directory=str(tmp_path), silent=True))
    request = FakeControlRequest(gui_protocol.Mark(type='mark', label='guitar solo'))
    rec.live = FakeControlDisplay([request])
    rec._start_manifest()

    rec._receive_control_requests()

    records = read_jsonl(manifest_path(rec))
    assert request.responses == [
        gui_protocol.Marked(type='marked', label='guitar solo')
    ]
    assert records[1] == {
        'type': 'mark',
        'timestamp': records[1]['timestamp'],
        'label': 'guitar solo',
    }


def test_control_request_sets_key_label(
    monkeypatch: pytest.MonkeyPatch,
    mock_devices: None,
) -> None:
    monkeypatch.setattr(recorder, 'DevicePoller', FakePoller)
    monkeypatch.setattr(recorder, 'SourceProcess', FakeSourceProcess)
    rec = Recorder(Cfg(include=['Mic'], silent=True))
    request = FakeControlRequest(
        gui_protocol.SetKeyLabel(type='set_key_label', key='g', label='guitar solo')
    )
    rec.live = FakeControlDisplay([request])

    rec._receive_control_requests()

    assert rec.cfg.keys.labels['g'] == 'guitar solo'
    assert request.responses == [
        gui_protocol.KeyLabelSet(type='key_label_set', key='g', label='guitar solo')
    ]


def test_control_request_pauses_and_resumes_recording(
    monkeypatch: pytest.MonkeyPatch,
    mock_devices: None,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(recorder, 'DevicePoller', FakePoller)
    monkeypatch.setattr(recorder, 'SourceProcess', FakeSourceProcess)
    rec = Recorder(Cfg(include=['Mic'], output_directory=str(tmp_path), silent=True))
    mic_info = next(info for info in DEVICES if info['name'] == 'Mic')
    assert rec._devices.poller is not None
    rec._devices.poller.snapshots = [{'Mic': mic_info}]
    rec._poll_devices()
    assert rec._devices.hardware['Mic'].running
    pause = FakeControlRequest(gui_protocol.PauseRecording(type='pause_recording'))
    resume = FakeControlRequest(gui_protocol.ResumeRecording(type='resume_recording'))
    rec.live = FakeControlDisplay([pause, resume])
    rec._start_manifest()

    rec._receive_control_requests()

    assert not rec._control.recording_paused
    assert not rec._devices.hardware['Mic'].running
    records = read_jsonl(manifest_path(rec))
    assert records[1]['type'] == 'recording_paused'
    assert records[2]['type'] == 'recording_resumed'


def test_control_request_reports_device_and_disk_status(
    monkeypatch: pytest.MonkeyPatch,
    mock_devices: None,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(recorder, 'DevicePoller', FakePoller)
    monkeypatch.setattr(recorder, 'SourceProcess', FakeSourceProcess)
    monkeypatch.setattr(
        disk_space_controller.shutil, 'disk_usage', lambda path: DiskUsage(100, 40, 60)
    )
    rec = Recorder(Cfg(include=['Mic'], output_directory=str(tmp_path), silent=True))
    devices = FakeControlRequest(gui_protocol.ListDevices(type='list_devices'))
    disk = FakeControlRequest(gui_protocol.DiskStatusRequest(type='disk_status'))
    status = FakeControlRequest(
        gui_protocol.StatusSnapshotRequest(type='status_snapshot')
    )
    rec.live = FakeControlDisplay([devices, disk, status])

    rec._receive_control_requests()

    assert devices.responses == [
        gui_protocol.Devices(
            type='devices',
            devices=[
                {
                    'channels': 1,
                    'name': 'Mic',
                    'online': False,
                    'sample_rate': 48000,
                }
            ],
        )
    ]
    assert disk.responses == [
        gui_protocol.DiskStatus(
            type='disk_status_result',
            free_bytes=60,
            path=str(tmp_path),
            total_bytes=100,
            used_bytes=40,
        )
    ]
    response = status.responses[0]
    assert isinstance(response, gui_protocol.StatusSnapshot)
    assert response.disk == disk.responses[0].model_dump(exclude={'type'})
    assert response.devices == devices.responses[0].devices
    assert response.errors == []
    assert response.recording == {'paused': False}


def test_status_snapshot_includes_error_timestamps(
    monkeypatch: pytest.MonkeyPatch,
    mock_devices: None,
) -> None:
    monkeypatch.setattr(recorder, 'DevicePoller', FakePoller)
    monkeypatch.setattr(recorder, 'SourceProcess', FakeSourceProcess)
    monkeypatch.setattr(recorder.times, 'timestamp', lambda: 100.0)
    rec = Recorder(Cfg(include=['Mic'], silent=True))
    rec._record_warning('Device Mic failed')

    response = rec._control.status_snapshot()

    assert response.errors == [
        ErrorRecord(
            timestamp='1970-01-01T00:01:40.000Z',
            message='Device Mic failed',
        )
    ]


def test_control_request_sets_and_gets_track_names(
    monkeypatch: pytest.MonkeyPatch,
    mock_devices: None,
) -> None:
    monkeypatch.setattr(recorder, 'DevicePoller', FakePoller)
    monkeypatch.setattr(recorder, 'SourceProcess', FakeSourceProcess)
    rec = Recorder(Cfg(include=['Mic'], silent=True))
    set_request = FakeControlRequest(
        gui_protocol.SetTrackNames(
            type='set_track_names', track_names={'Mic': {'Lead Vocal': 1}}
        )
    )
    get_request = FakeControlRequest(gui_protocol.GetTrackNames(type='get_track_names'))
    rec.live = FakeControlDisplay([set_request, get_request])

    rec._receive_control_requests()

    expected = gui_protocol.TrackNames(
        type='track_names', track_names={'Mic': {'Lead Vocal': 1}}
    )
    assert set_request.responses == [expected]
    assert get_request.responses == [expected]
    assert rec._devices.sources['Mic'].track_names == {'Mic': {'Lead Vocal': 1}}


def test_control_request_sets_and_gets_cfg(
    monkeypatch: pytest.MonkeyPatch,
    mock_devices: None,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(recorder, 'DevicePoller', FakePoller)
    monkeypatch.setattr(recorder, 'SourceProcess', FakeSourceProcess)
    rec = Recorder(Cfg(include=['Mic'], output_directory=str(tmp_path), silent=True))
    set_request = FakeControlRequest(
        gui_protocol.SetCfg(
            type='set_cfg', address='recording.longest_file_time', value=3600
        )
    )
    get_request = FakeControlRequest(
        gui_protocol.GetCfg(type='get_cfg', address='recording.longest_file_time')
    )
    rec.live = FakeControlDisplay([set_request, get_request])
    rec._start_manifest()

    rec._receive_control_requests()

    expected = 3600.0
    assert rec.cfg.recording.longest_file_time == expected
    assert rec._devices.sources['Mic'].cfg is rec.cfg
    assert set_request.responses == [
        gui_protocol.CfgSet(
            type='cfg_set', address='recording.longest_file_time', value=expected
        )
    ]
    assert get_request.responses == [
        gui_protocol.CfgValue(
            type='cfg_value', address='recording.longest_file_time', value=expected
        )
    ]
    records = read_jsonl(manifest_path(rec))
    assert [record['type'] for record in records[1:3]] == ['cfg_set', 'cfg_get']
    assert records[1]['cfg_revision'] == 1


def test_source_update_records_applied_cfg_revision(
    monkeypatch: pytest.MonkeyPatch,
    mock_devices: None,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(recorder, 'DevicePoller', FakePoller)
    monkeypatch.setattr(recorder, 'SourceProcess', FakeSourceProcess)
    rec = Recorder(Cfg(include=['Mic'], output_directory=str(tmp_path), silent=True))
    rec._start_manifest()

    rec._receive_update(
        SourceUpdate(
            channels={'1': ChannelState()},
            files=[],
            frames=0,
            source_name='Mic',
            config_revisions_applied=[3],
        )
    )

    records = read_jsonl(manifest_path(rec))
    assert records[1]['type'] == 'cfg_applied'
    assert records[1]['source'] == 'Mic'
    assert records[1]['value'] == 3


def test_buffer_overflow_records_write_latency(
    monkeypatch: pytest.MonkeyPatch,
    mock_devices: None,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(recorder, 'DevicePoller', FakePoller)
    monkeypatch.setattr(recorder, 'SourceProcess', FakeSourceProcess)
    rec = Recorder(Cfg(include=['Mic'], output_directory=str(tmp_path), silent=True))
    rec._start_manifest()

    rec._record_device_buffer_update(
        'Mic',
        BufferStats(
            dropped_blocks=1,
            dropped_frames=2,
            last_drop_timestamp=3.0,
            max_write_seconds=0.25,
        ),
    )

    records = read_jsonl(manifest_path(rec))
    assert records[1]['type'] == 'buffer_overflow'
    assert records[1]['max_write_seconds'] == 0.25


def test_save_settings_failure_records_warning(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    records: list[object] = []
    control = object.__new__(recorder.recording_control.RecordingControl)
    control.cfg = Cfg(save_settings=True)
    control.track_names = {}
    control.saved_tracks = {}
    control.write_record = records.append
    monkeypatch.setattr(
        recording_track_config.settings,
        'save',
        lambda cfg, track_names, tracks: _raise_recs_error('cannot save settings'),
    )

    recording_track_config.save_settings(control)

    assert records[0].message == 'cannot save settings'


def _raise_recs_error(message: str) -> None:
    raise RecsError(message)


def test_control_request_reports_mutable_attributes(
    monkeypatch: pytest.MonkeyPatch,
    mock_devices: None,
) -> None:
    monkeypatch.setattr(recorder, 'DevicePoller', FakePoller)
    monkeypatch.setattr(recorder, 'SourceProcess', FakeSourceProcess)
    rec = Recorder(Cfg(include=['Mic'], silent=True))
    request = FakeControlRequest(
        gui_protocol.MutableAttributes(type='mutable_attributes')
    )
    rec.live = FakeControlDisplay([request])

    rec._receive_control_requests()

    assert request.responses == [
        gui_protocol.MutableAttributesResult(
            type='mutable_attributes_result',
            mutable_attributes=sorted(rec.cfg.mutable_attributes),
        )
    ]


def test_control_request_rejects_immutable_cfg(
    monkeypatch: pytest.MonkeyPatch,
    mock_devices: None,
) -> None:
    monkeypatch.setattr(recorder, 'DevicePoller', FakePoller)
    monkeypatch.setattr(recorder, 'SourceProcess', FakeSourceProcess)
    rec = Recorder(Cfg(include=['Mic'], silent=True))
    request = FakeControlRequest(
        gui_protocol.SetCfg(
            type='set_cfg', address='recording.memory_reserve_megabytes', value=4
        )
    )
    rec.live = FakeControlDisplay([request])

    rec._receive_control_requests()

    assert request.responses == [
        gui_protocol.Error(
            type='error',
            message=(
                'Immutable configuration attribute: '
                'recording.memory_reserve_megabytes'
            ),
        )
    ]


def test_control_request_reload_profiles(
    monkeypatch: pytest.MonkeyPatch,
    mock_devices: None,
    tmp_path: Path,
) -> None:
    profiles = tmp_path / 'profiles.json'
    profiles.write_text('{"Mic": {"noise_floor": 42.5}}')
    monkeypatch.setattr(recorder, 'DevicePoller', FakePoller)
    monkeypatch.setattr(recorder, 'SourceProcess', FakeSourceProcess)
    rec = Recorder(Cfg(profiles=profiles, include=['Mic'], silent=True))
    request = FakeControlRequest(gui_protocol.ReloadProfiles(type='reload_profiles'))
    rec.live = FakeControlDisplay([request])

    rec._receive_control_requests()

    assert request.responses == [
        gui_protocol.ProfilesReloaded(
            type='profiles_reloaded', profiles_path=str(profiles)
        )
    ]


def test_empty_template_output_directory_manifest_uses_time_template(
    monkeypatch: pytest.MonkeyPatch,
    mock_devices: None,
    tmp_path: Path,
) -> None:
    timestamp = datetime(2026, 6, 23, 20, 34, 10).timestamp()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(recorder.times, 'timestamp', lambda: timestamp)
    monkeypatch.setattr(recorder, 'DevicePoller', FakePoller)
    monkeypatch.setattr(recorder, 'SourceProcess', FakeSourceProcess)
    rec = Recorder(Cfg(include=['Mic'], output_directory='sessions/{sdate}'))
    rec._start_manifest()

    assert Path(
        'sessions/2026-06-23/2026-06-23 20-34-10/audio/audio-manifest.jsonl'
    ).exists()


def test_default_output_directory_uses_session_timestamp(
    monkeypatch: pytest.MonkeyPatch,
    mock_devices: None,
    tmp_path: Path,
) -> None:
    timestamp = datetime(2026, 6, 23, 20, 34, 10).timestamp()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(recorder.times, 'timestamp', lambda: timestamp)
    monkeypatch.setattr(recorder, 'SourceProcess', FakeSourceProcess)

    rec = Recorder(Cfg(include=['Mic'], silent=True))
    rec._start_manifest()
    expected = recording_paths.session_directory_name(timestamp)
    path = rec.session_directory / 'audio/mic.wav'
    path.parent.mkdir(exist_ok=True, parents=True)
    path.touch()

    rec._receive_update(
        SourceUpdate(
            channels={'1': ChannelState()},
            files=[path],
            frames=48_000,
            source_name='Mic',
            file_records=[
                SourceFile(
                    path=path,
                    source_name='Mic',
                    track=1,
                    channels=1,
                    sample_rate=48_000,
                    bit_depth=64,
                )
            ],
        )
    )
    rec._finish_manifest()

    assert rec.cfg.directory.output_directory == ''
    assert rec.session_directory == Path(expected)
    assert (path.parent / 'audio-manifest.jsonl').exists()


def test_default_output_directory_uses_collision_suffix(
    monkeypatch: pytest.MonkeyPatch,
    mock_devices: None,
    tmp_path: Path,
) -> None:
    timestamp = datetime(2026, 6, 23, 20, 34, 10).timestamp()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(recorder.times, 'timestamp', lambda: timestamp)
    monkeypatch.setattr(recorder, 'SourceProcess', FakeSourceProcess)
    expected = recording_paths.session_directory_name(timestamp)
    Path(expected).mkdir()

    rec = Recorder(Cfg(include=['Mic'], silent=True))

    assert rec.cfg.directory.output_directory == ''
    assert rec.session_directory == Path(f'{expected}_1')


def test_daemon_default_output_directory_uses_largest_external_disk(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    small = tmp_path / 'small'
    large = tmp_path / 'large'
    monkeypatch.setattr(recorder.gui_ipc, 'daemon_mode_enabled', lambda: True)
    monkeypatch.setattr(recording_paths, 'mounted_record_disks', lambda: [small, large])
    monkeypatch.setattr(
        recording_paths.shutil,
        'disk_usage',
        lambda p: DiskUsage(100, 50, 10 if p == small else 90),
    )

    timestamp = datetime(2026, 6, 23, 20, 34, 10).timestamp()
    cfg = recording_paths.with_default_output_directory(
        Cfg(default_record_directory='takes'), timestamp
    )

    assert cfg.directory.output_directory == str(large / 'takes')
    assert recording_paths.session_directory(str(large / 'takes'), timestamp) == (
        large / 'takes' / '2026-06-23 20-34-10'
    )
    assert recording_paths.media_session_directory(
        large / 'takes' / '2026-06-23 20-34-10', 'midi'
    ) == (large / 'takes' / '2026-06-23 20-34-10' / 'midi')


def test_daemon_default_output_directory_falls_back_to_system_disk(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(recorder.gui_ipc, 'daemon_mode_enabled', lambda: True)
    monkeypatch.setattr(recording_paths, 'mounted_record_disks', lambda: [])
    monkeypatch.setattr(recording_paths.Path, 'home', lambda: tmp_path)

    timestamp = datetime(2026, 6, 23, 20, 34, 10).timestamp()
    cfg = recording_paths.with_default_output_directory(Cfg(), timestamp)

    assert cfg.directory.output_directory == str(tmp_path / 'recs')


def test_daemon_default_output_directory_keeps_explicit_directory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(recorder.gui_ipc, 'daemon_mode_enabled', lambda: True)

    cfg = recording_paths.with_default_output_directory(
        Cfg(output_directory='manual'), 0
    )

    assert cfg.directory.output_directory == 'manual'


def test_default_output_directory_replaces_problematic_characters() -> None:
    timestamp = datetime(2026, 6, 23, 20, 34, 10).timestamp()

    assert recording_paths.session_directory_name(timestamp) == '2026-06-23 20-34-10'


def test_manifest_records_source_and_track_lifecycle_events(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    now = 100.0

    def timestamp() -> float:
        nonlocal now
        now += 1.0
        return now

    monkeypatch.setattr(recorder.times, 'timestamp', timestamp)
    monkeypatch.setattr(recorder, 'DevicePoller', FakePoller)
    monkeypatch.setattr(recorder, 'SourceProcess', FakeSourceProcess)
    rec = Recorder(
        Cfg(
            devices=Path(DEVICES_FILE),
            include=['Mic'],
            output_directory=str(tmp_path),
            silent=True,
        )
    )
    rec._start_manifest()
    mic_info = next(info for info in DEVICES if info['name'] == 'Mic')
    rec._devices.poller.snapshots = [{'Mic': mic_info}, {}, {'Mic': mic_info}]

    rec._poll_devices()
    rec._receive_update(
        SourceUpdate(
            channels={'1': ChannelState(is_active=True)},
            files=[],
            frames=48_000,
            source_name='Mic',
        )
    )
    rec._receive_update(
        SourceUpdate(
            channels={'1': ChannelState(is_active=False)},
            files=[],
            frames=240_000,
            source_name='Mic',
        )
    )
    rec._poll_devices()
    rec._reap_sources()
    rec._poll_devices()
    records = read_jsonl(manifest_path(rec))
    assert records[1:] == [
        {
            'timestamp': '1970-01-01T00:01:43.000Z',
            'type': 'source_online',
            'source': 'Mic',
            'start_frame': 0,
        },
        {
            'timestamp': '1970-01-01T00:01:44.000Z',
            'type': 'track_started',
            'source': 'Mic',
            'track': '1',
        },
        {
            'timestamp': '1970-01-01T00:01:46.000Z',
            'type': 'track_stopped',
            'source': 'Mic',
            'track': '1',
        },
        {
            'timestamp': '1970-01-01T00:01:48.000Z',
            'type': 'warning',
            'message': 'Device Mic went offline',
        },
        {
            'timestamp': '1970-01-01T00:01:49.000Z',
            'type': 'source_offline',
            'source': 'Mic',
        },
        {
            'timestamp': '1970-01-01T00:01:51.000Z',
            'type': 'source_online',
            'source': 'Mic',
            'start_frame': 288000,
        },
    ]


def test_manifest_records_key_events(
    monkeypatch: pytest.MonkeyPatch,
    mock_devices: None,
    tmp_path: Path,
) -> None:
    now = 100.0

    def timestamp() -> float:
        nonlocal now
        now += 1.0
        return now

    monkeypatch.setattr(recorder.times, 'timestamp', timestamp)
    monkeypatch.setattr(recorder, 'DevicePoller', FakePoller)
    monkeypatch.setattr(recorder, 'SourceProcess', FakeSourceProcess)
    rec = Recorder(
        Cfg(
            key_label=['g=guitar too soft'],
            output_directory=str(tmp_path),
            silent=True,
        )
    )
    rec._start_manifest()
    rec.key_recorder = FakeKeyRecorder(
        [
            KeyEvent(type='key_pressed', key='g'),
            KeyEvent(type='key_released', key='g'),
        ]
    )

    rec._receive_key_events()
    records = read_jsonl(manifest_path(rec))
    assert records[1:] == [
        {
            'timestamp': '1970-01-01T00:01:42.000Z',
            'type': 'key_pressed',
            'key': 'g',
            'label': 'guitar too soft',
        },
        {
            'timestamp': '1970-01-01T00:01:43.000Z',
            'type': 'key_released',
            'key': 'g',
            'label': 'guitar too soft',
        },
    ]


def test_recorder_summary_formats_short_time() -> None:
    assert recorder._summary_time(4.143) == '0:04.143'
