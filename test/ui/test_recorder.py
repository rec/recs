import json
import typing
from datetime import datetime
from pathlib import Path
from test.conftest import DEVICES, DEVICES_FILE

import pytest
from threa import Runnable

from recs.base.state import ChannelState
from recs.cfg import device
from recs.cfg.cfg import Cfg
from recs.cfg.track import Track
from recs.daemon import gui_protocol
from recs.ui import recorder
from recs.ui.key_events import KeyEvent
from recs.ui.recorder import Recorder
from recs.ui.source_recorder import BufferStats, SourceFailure, SourceFile, SourceUpdate


class DiskUsage(typing.NamedTuple):
    total: int
    used: int
    free: int


class FakePoller(Runnable):
    def __init__(self, interval: float) -> None:
        self.snapshots: list[dict[str, typing.Any] | None] = []

    def latest(self) -> dict[str, typing.Any] | None:
        return self.snapshots.pop(0) if self.snapshots else None

    def poll(self) -> None:
        pass


def read_jsonl(path: Path) -> list[dict[str, typing.Any]]:
    return [json.loads(line) for line in path.read_text().splitlines()]


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
        tracks: typing.Sequence[Track],
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

    def set_cfg(self, cfg: Cfg) -> None:
        self.cfg = cfg

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
        rows: typing.Callable[[], typing.Iterator[typing.Mapping[str, object]]],
        cfg: Cfg,
        *,
        errors: typing.Callable[[], typing.Iterable[str]] | None = None,
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
    capsys: pytest.CaptureFixture[str],
    mock_devices: None,
) -> None:
    monkeypatch.setattr(recorder, 'DevicePoller', FakePoller)
    monkeypatch.setattr(recorder, 'SourceProcess', FakeSourceProcess)

    rec = Recorder(Cfg(include=['e'], exclude=['e'], silent=True))

    assert rec.warnings == ['No channels selected']
    assert rec.error_messages() == ['No channels selected']
    assert capsys.readouterr().err == 'ERROR: No channels selected\n'


def test_recorder_runs_without_devices(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(device, 'query_devices', lambda: [])
    monkeypatch.setattr(recorder, 'DevicePoller', FakePoller)
    monkeypatch.setattr(recorder, 'SourceProcess', FakeSourceProcess)

    rec = Recorder(Cfg(silent=True))

    assert rec.hardware == {}
    assert rec.poller is not None
    assert rec.warnings == ['No input devices detected']
    assert rec.error_messages() == ['No input devices detected']
    assert capsys.readouterr().err == 'ERROR: No input devices detected\n'


def test_recorder_adds_device_detected_after_start(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(device, 'query_devices', lambda: [])
    monkeypatch.setattr(recorder, 'DevicePoller', FakePoller)
    monkeypatch.setattr(recorder, 'SourceProcess', FakeSourceProcess)
    rec = Recorder(Cfg(include=['Mic'], silent=True))
    mic_info = next(info for info in DEVICES if info['name'] == 'Mic')
    assert rec.poller is not None
    rec.poller.snapshots = [{'Mic': mic_info}]
    capsys.readouterr()

    rec._poll_devices()

    assert 'Mic' in rec.hardware
    assert rec.hardware['Mic'].started
    assert list(rec.state.state) == ['Mic']


def test_recorder_replaces_returning_device(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(recorder, 'DevicePoller', FakePoller)
    monkeypatch.setattr(recorder, 'SourceProcess', FakeSourceProcess)
    rec = Recorder(Cfg(devices=Path(DEVICES_FILE), silent=True))
    mic_info = next(info for info in DEVICES if info['name'] == 'Mic')
    mic = rec.hardware['Mic']

    rec.poller.snapshots = [
        {},
        {'Mic': mic_info, 'Unexpected': mic_info},
        {},
        {'Mic': mic_info},
    ]

    rec._poll_devices()
    assert not any(source.started for source in rec.hardware.values())

    rec._poll_devices()
    assert mic.started
    assert mic.start_count == 1
    assert not any(
        source.started for name, source in rec.hardware.items() if name != 'Mic'
    )

    rec._poll_devices()
    rec._reap_sources()
    assert not mic.started
    assert 'Device Mic went offline' in rec.warnings
    assert 'ERROR: Device Mic went offline\n' in capsys.readouterr().err

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
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(recorder, 'DevicePoller', FakePoller)
    monkeypatch.setattr(recorder, 'SourceProcess', FakeSourceProcess)
    monkeypatch.setattr(recorder.live, 'Live', ClosedDisplay)
    rec = Recorder(Cfg(devices=Path(DEVICES_FILE)))
    flower = rec.hardware['Flower 8']
    rec.poller.snapshots = [{'Flower 8': {'max_input_channels': 2, 'name': 'Flower 8'}}]

    rec._poll_devices()

    assert rec.live is not None
    assert rec.live.errors() == ['Flower 8 has 2 input channels; 10 required']
    assert capsys.readouterr().err == (
        'ERROR: Flower 8 has 2 input channels; 10 required\n'
    )
    assert not flower.started


def test_gui_starts_sources_before_display_process(
    monkeypatch: pytest.MonkeyPatch,
    mock_devices: None,
) -> None:
    rec: Recorder

    class OrderDisplay(ClosedDisplay):
        def start(self) -> None:
            assert any(source.started for source in rec.hardware.values())
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


def test_failed_device_waits_for_reconnect(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(recorder, 'DevicePoller', FakePoller)
    monkeypatch.setattr(recorder, 'SourceProcess', FakeSourceProcess)
    rec = Recorder(Cfg(devices=Path(DEVICES_FILE), silent=True))
    mic_info = next(info for info in DEVICES if info['name'] == 'Mic')
    mic = rec.hardware['Mic']
    rec.poller.snapshots = [
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
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(recorder, 'DevicePoller', FakePoller)
    monkeypatch.setattr(recorder, 'SourceProcess', FakeSourceProcess)
    rec = Recorder(Cfg(devices=Path(DEVICES_FILE), silent=True))
    flower = rec.hardware['Flower 8']
    rec.poller.snapshots = [{'Flower 8': {'max_input_channels': 2, 'name': 'Flower 8'}}]

    rec._poll_devices()

    assert not flower.started
    assert capsys.readouterr().err == (
        'ERROR: Flower 8 has 2 input channels; 10 required\n'
    )


def test_slow_device_clock_stays_offline(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    now = 100.0
    monkeypatch.setattr(recorder.times, 'timestamp', lambda: now)
    monkeypatch.setattr(recorder, 'DevicePoller', FakePoller)
    monkeypatch.setattr(recorder, 'SourceProcess', FakeSourceProcess)
    rec = Recorder(Cfg(devices=Path(DEVICES_FILE), include=['Mic'], silent=True))
    mic_info = next(info for info in DEVICES if info['name'] == 'Mic')
    mic = rec.hardware['Mic']
    rec.poller.snapshots = [{'Mic': mic_info}]

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
    assert 'Mic' in rec.failed
    assert capsys.readouterr().err == 'Device Mic lagging behind real time\n'


def test_slow_device_clock_reports_once_per_session(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    now = 100.0
    monkeypatch.setattr(recorder.times, 'timestamp', lambda: now)
    monkeypatch.setattr(recorder, 'DevicePoller', FakePoller)
    monkeypatch.setattr(recorder, 'SourceProcess', FakeSourceProcess)
    rec = Recorder(Cfg(devices=Path(DEVICES_FILE), include=['Mic'], silent=True))
    mic_info = next(info for info in DEVICES if info['name'] == 'Mic')
    mic = rec.hardware['Mic']
    rec.poller.snapshots = [{'Mic': mic_info}]
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

    assert capsys.readouterr().err == 'Device Mic lagging behind real time\n'


def test_slow_device_clock_ignores_startup_grace(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    now = 100.0
    monkeypatch.setattr(recorder.times, 'timestamp', lambda: now)
    monkeypatch.setattr(recorder, 'DevicePoller', FakePoller)
    monkeypatch.setattr(recorder, 'SourceProcess', FakeSourceProcess)
    rec = Recorder(Cfg(devices=Path(DEVICES_FILE), include=['Mic'], silent=True))
    mic_info = next(info for info in DEVICES if info['name'] == 'Mic')
    mic = rec.hardware['Mic']
    rec.poller.snapshots = [{'Mic': mic_info}]

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
    assert 'Mic' not in rec.failed
    assert capsys.readouterr().err == ''


def test_stalled_source_is_stopped(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    now = 100.0
    monkeypatch.setattr(recorder.times, 'timestamp', lambda: now)
    monkeypatch.setattr(recorder, 'DevicePoller', FakePoller)
    monkeypatch.setattr(recorder, 'SourceProcess', FakeSourceProcess)
    rec = Recorder(Cfg(devices=Path(DEVICES_FILE), include=['Mic'], silent=True))
    mic_info = next(info for info in DEVICES if info['name'] == 'Mic')
    mic = rec.hardware['Mic']
    rec.poller.snapshots = [{'Mic': mic_info}]

    rec._poll_devices()
    now += recorder.SOURCE_STALL_TIMEOUT + 1
    rec._stop_stalled_sources()

    assert not mic.started
    assert 'Mic' in rec.failed
    assert rec.warnings == ['Device Mic stopped sending updates']
    assert capsys.readouterr().err == 'Device Mic stopped sending updates\n'


def test_source_failure_is_reported(
    monkeypatch: pytest.MonkeyPatch,
    mock_devices: None,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(recorder, 'SourceProcess', FakeSourceProcess)
    rec = Recorder(Cfg(devices=Path(DEVICES_FILE), include=['Mic'], silent=True))

    rec._receive_source_message(
        SourceFailure(message='ValueError: no input device', source_name='Mic')
    )

    assert rec.warnings == ['Device Mic failed: ValueError: no input device']
    assert 'Mic' in rec.failed
    assert capsys.readouterr().err == (
        'Device Mic failed: ValueError: no input device\n'
    )


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

    records = read_jsonl(tmp_path / 'recs-session.jsonl')
    assert records[1] == {
        'type': 'buffer_overflow',
        'timestamp': '1970-01-01T00:00:00.000Z',
        'dropped_blocks': 1,
        'dropped_frames': 512,
        'source': 'Mic',
        'max_queued_seconds': 0.5,
        'queued_seconds': 0.25,
    }


def test_recorder_rows_include_buffer_stats(
    monkeypatch: pytest.MonkeyPatch,
    mock_devices: None,
) -> None:
    monkeypatch.setattr(recorder, 'DevicePoller', FakePoller)
    monkeypatch.setattr(recorder, 'SourceProcess', FakeSourceProcess)
    rec = Recorder(Cfg(include=['Mic'], silent=True))
    rec.buffer_stats['Mic'] = BufferStats(queued_seconds=0.25, dropped_frames=512)

    rows = list(rec.rows())

    assert rows[1]['buffer'] == 0.25
    assert rows[1]['dropped'] == 512


def test_recorder_reports_low_disk_space_once(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    mock_devices: None,
) -> None:
    monkeypatch.setattr(recorder, 'DevicePoller', FakePoller)
    monkeypatch.setattr(recorder, 'SourceProcess', FakeSourceProcess)
    monkeypatch.setattr(
        recorder.shutil, 'disk_usage', lambda path: DiskUsage(100, 96, 4)
    )
    rec = Recorder(Cfg(minimum_free_space=5, silent=True))

    assert rec._disk_space_low()
    assert rec._disk_space_low()
    assert rec.warnings == ['Free disk space 4 bytes is below minimum_free_space=5']
    assert capsys.readouterr().err == (
        'Free disk space 4 bytes is below minimum_free_space=5\n'
    )


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
    rec.files_written.update(files)
    rec.session_files_written.update(files)
    monkeypatch.setattr(recorder.times, 'timestamp', lambda: 165.25)

    def interrupt() -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr(rec, '_run', interrupt)

    rec.run()

    assert capsys.readouterr() == (
        f'Recording time: 1:05.250\nFiles written:\n  {first}\n  {second}\n',
        'Interrupted\n',
    )


def test_recorder_explains_dry_run_without_files(
    monkeypatch: pytest.MonkeyPatch,
    mock_devices: None,
) -> None:
    monkeypatch.setattr(recorder, 'DevicePoller', FakePoller)
    monkeypatch.setattr(recorder, 'SourceProcess', FakeSourceProcess)
    rec = Recorder(Cfg(dry_run=True, include=['Mic'], silent=True))

    assert rec._no_file_explanation() == 'dry-run mode does not write files'


def test_recorder_explains_missing_audio_updates(
    monkeypatch: pytest.MonkeyPatch,
    mock_devices: None,
) -> None:
    monkeypatch.setattr(recorder, 'DevicePoller', FakePoller)
    monkeypatch.setattr(recorder, 'SourceProcess', FakeSourceProcess)
    rec = Recorder(Cfg(include=['Mic'], silent=True))

    assert rec._no_file_explanation() == 'no audio updates were received'


def test_recorder_explains_quiet_or_short_audio(
    monkeypatch: pytest.MonkeyPatch,
    mock_devices: None,
) -> None:
    monkeypatch.setattr(recorder, 'DevicePoller', FakePoller)
    monkeypatch.setattr(recorder, 'SourceProcess', FakeSourceProcess)
    rec = Recorder(Cfg(include=['Mic'], silent=True))
    rec.frames['Mic'] = 48_000

    assert rec._no_file_explanation() == (
        'audio stayed below the noise floor or candidate files were shorter '
        'than shortest_file_time'
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
    rec.files_written.add(path)

    assert rec._output_folder() == path.parent


def test_open_folder_uses_platform_file_manager(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    commands: list[list[str]] = []
    monkeypatch.setattr(recorder.sys, 'platform', 'darwin')
    monkeypatch.setattr(
        recorder.subprocess,
        'run',
        lambda command, check: commands.append(command),
    )

    recorder._open_folder(tmp_path)

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
    path = tmp_path / 'mic.wav'
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

    records = read_jsonl(tmp_path / 'recs-session.jsonl')
    for record in records:
        record.pop('timestamp', None)
    assert records[1:3] == [
        {
            'type': 'file_started',
            'path': path.as_posix(),
            'track': 1,
            'channels': 1,
            'sample_rate': 48_000,
            'bit_depth': 64,
        },
        {
            'type': 'file_finished',
            'path': path.as_posix(),
            'track': 1,
            'channels': 1,
            'sample_rate': 48_000,
            'bit_depth': 64,
        },
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
    path = tmp_path / 'mic.wav'
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

    records = read_jsonl(tmp_path / 'recs-session.jsonl')
    for record in records:
        record.pop('timestamp', None)
    assert records[1:4] == [
        {
            'type': 'file_started',
            'frame_count': 256,
            'path': path.as_posix(),
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
            'frame_count': 768,
            'path': path.as_posix(),
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

    assert not Path('recs-session.jsonl').exists()


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
    rec.hardware['Mic'].start()
    request = FakeControlRequest()
    rec.live = FakeControlDisplay([request])

    rec._receive_control_requests()

    assert all(source.cfg is rec.cfg for source in rec.sources.values())
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
    rec.hardware['Ext'].start()

    assert rec._calibration_tracks({'Ext': [1]}) == {'Ext': ['1-2']}


def test_control_request_splits_stereo_track_and_records_event(
    monkeypatch: pytest.MonkeyPatch,
    mock_devices: None,
) -> None:
    records: list[object] = []
    monkeypatch.setattr(recorder, 'DevicePoller', FakePoller)
    monkeypatch.setattr(recorder, 'SourceProcess', FakeSourceProcess)
    rec = Recorder(
        Cfg(
            include=['Ext'],
            channel_noise_floors={'Ext': {'1-2': 37}},
            silent=True,
        )
    )
    monkeypatch.setattr(rec, '_write_manifest_record', records.append)
    request = FakeControlRequest(
        gui_protocol.SetTracks(
            type='set_tracks',
            source='Ext',
            tracks=[
                gui_protocol.ChannelTrack(channels=[1], name='VL'),
                gui_protocol.ChannelTrack(channels=[2]),
            ],
        )
    )
    rec.live = FakeControlDisplay([request])

    rec._receive_control_requests()

    assert [track.name for track in rec.sources['Ext'].tracks] == ['1', '2', '3']
    assert rec.track_names == {'Ext': {'VL': 1}}
    assert rec.cfg.recording.channel_noise_floors == {'Ext': {'1': 37, '2': 37}}
    assert request.responses == [
        gui_protocol.TracksSet(
            type='tracks_set',
            source='Ext',
            tracks=[
                gui_protocol.ChannelTrack(channels=[1], name='VL'),
                gui_protocol.ChannelTrack(channels=[2]),
            ],
        )
    ]
    assert [record.type for record in records] == ['cfg_set', 'tracks_set']
    assert records[1].source == 'Ext'


def test_control_request_groups_mono_tracks_into_stereo_pair(
    monkeypatch: pytest.MonkeyPatch,
    mock_devices: None,
) -> None:
    monkeypatch.setattr(recorder, 'DevicePoller', FakePoller)
    monkeypatch.setattr(recorder, 'SourceProcess', FakeSourceProcess)
    rec = Recorder(
        Cfg(
            include=['Ext+1', 'Ext+2'],
            channel_noise_floors={'Ext': {'1': 37, '2': 37}},
            silent=True,
        )
    )
    request = FakeControlRequest(
        gui_protocol.SetTracks(
            type='set_tracks',
            source='Ext',
            tracks=[gui_protocol.ChannelTrack(channels=[1, 2], name='Stereo')],
        )
    )
    rec.live = FakeControlDisplay([request])

    rec._receive_control_requests()

    assert [track.name for track in rec.sources['Ext'].tracks] == ['1-2']
    assert rec.track_names == {'Ext': {'Stereo': 1}}
    assert rec.cfg.recording.channel_noise_floors == {'Ext': {'1-2': 37}}


def test_track_layout_updates_state_on_next_source_update(
    monkeypatch: pytest.MonkeyPatch,
    mock_devices: None,
) -> None:
    monkeypatch.setattr(recorder, 'DevicePoller', FakePoller)
    monkeypatch.setattr(recorder, 'SourceProcess', FakeSourceProcess)
    rec = Recorder(Cfg(include=['Ext'], silent=True))
    source = rec.sources['Ext']
    rec.track_names = {'Ext': {'VL': 1}}
    source.set_tracks(
        [
            Track(source.source, '1'),
            Track(source.source, '2'),
            Track(source.source, '3'),
        ],
        rec.track_names,
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


def test_control_request_rejects_partial_stereo_track_replacement(
    monkeypatch: pytest.MonkeyPatch,
    mock_devices: None,
) -> None:
    monkeypatch.setattr(recorder, 'DevicePoller', FakePoller)
    monkeypatch.setattr(recorder, 'SourceProcess', FakeSourceProcess)
    rec = Recorder(Cfg(include=['Ext'], silent=True))
    request = FakeControlRequest(
        gui_protocol.SetTracks(
            type='set_tracks',
            source='Ext',
            tracks=[gui_protocol.ChannelTrack(channels=[1], name='VL')],
        )
    )
    rec.live = FakeControlDisplay([request])

    rec._receive_control_requests()

    assert request.responses == [
        gui_protocol.Error(
            type='error',
            message='All channels in Ext + 1-2 must be replaced together',
        )
    ]


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
    assert response.version == 2
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

    records = read_jsonl(tmp_path / 'recs-session.jsonl')
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
    assert rec.poller is not None
    rec.poller.snapshots = [{'Mic': mic_info}]
    rec._poll_devices()
    assert rec.hardware['Mic'].running
    pause = FakeControlRequest(gui_protocol.PauseRecording(type='pause_recording'))
    resume = FakeControlRequest(gui_protocol.ResumeRecording(type='resume_recording'))
    rec.live = FakeControlDisplay([pause, resume])
    rec._start_manifest()

    rec._receive_control_requests()

    assert not rec.recording_paused
    assert not rec.recording_stopped
    assert not rec.hardware['Mic'].running
    records = read_jsonl(tmp_path / 'recs-session.jsonl')
    assert records[1]['type'] == 'recording_paused'
    assert records[2]['type'] == 'recording_resumed'


def test_control_request_stops_and_starts_recording(
    monkeypatch: pytest.MonkeyPatch,
    mock_devices: None,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(recorder, 'DevicePoller', FakePoller)
    monkeypatch.setattr(recorder, 'SourceProcess', FakeSourceProcess)
    rec = Recorder(Cfg(include=['Mic'], silent=True))
    stop = FakeControlRequest(gui_protocol.StopRecording(type='stop_recording'))
    start = FakeControlRequest(gui_protocol.StartRecording(type='start_recording'))
    rec.live = FakeControlDisplay([stop, start])

    rec._receive_control_requests()

    assert stop.responses == [
        gui_protocol.RecordingState(type='recording_state', paused=True, stopped=True)
    ]
    assert start.responses == [
        gui_protocol.RecordingState(type='recording_state', paused=False, stopped=False)
    ]


def test_daemon_start_after_stop_uses_new_session_directory(
    monkeypatch: pytest.MonkeyPatch,
    mock_devices: None,
    tmp_path: Path,
) -> None:
    first = datetime(2026, 6, 23, 20, 34, 10).timestamp()
    second = datetime(2026, 6, 23, 21, 34, 10).timestamp()
    times = iter([first, first, first, second, second])
    monkeypatch.setattr(recorder.times, 'timestamp', lambda: next(times))
    monkeypatch.setattr(recorder, 'DevicePoller', FakePoller)
    monkeypatch.setattr(recorder, 'SourceProcess', FakeSourceProcess)
    monkeypatch.setattr(recorder.gui_ipc, 'daemon_mode_enabled', lambda: True)
    monkeypatch.setattr(recorder, '_mounted_record_disks', lambda: [tmp_path])

    rec = Recorder(Cfg(include=['Mic'], silent=True))
    rec._start_manifest()
    first_manifest = tmp_path / 'recs' / '2026-06-23 20:34:10' / 'recs-session.jsonl'

    rec._stop_recording()
    rec._stop_recording()
    rec._resume_recording('start_recording')

    second_manifest = tmp_path / 'recs' / '2026-06-23 21:34:10' / 'recs-session.jsonl'
    assert first_manifest.exists()
    assert read_jsonl(first_manifest)[-1]['type'] == 'footer'
    assert second_manifest.exists()


def test_control_request_reports_device_and_disk_status(
    monkeypatch: pytest.MonkeyPatch,
    mock_devices: None,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(recorder, 'DevicePoller', FakePoller)
    monkeypatch.setattr(recorder, 'SourceProcess', FakeSourceProcess)
    monkeypatch.setattr(
        recorder.shutil, 'disk_usage', lambda path: DiskUsage(100, 40, 60)
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
    assert response.recording == {'paused': False, 'stopped': False}


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
    assert rec.sources['Mic'].track_names == {'Mic': {'Lead Vocal': 1}}


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
    assert rec.sources['Mic'].cfg is rec.cfg
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
    records = read_jsonl(tmp_path / 'recs-session.jsonl')
    assert [record['type'] for record in records[1:3]] == ['cfg_set', 'cfg_get']


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
            type='set_cfg', address='recording.audio_buffer_seconds', value=4
        )
    )
    rec.live = FakeControlDisplay([request])

    rec._receive_control_requests()

    assert request.responses == [
        gui_protocol.Error(
            type='error',
            message='Immutable configuration attribute: recording.audio_buffer_seconds',
        )
    ]


def test_control_request_rejects_invalid_track_names(
    monkeypatch: pytest.MonkeyPatch,
    mock_devices: None,
) -> None:
    monkeypatch.setattr(recorder, 'DevicePoller', FakePoller)
    monkeypatch.setattr(recorder, 'SourceProcess', FakeSourceProcess)
    rec = Recorder(Cfg(include=['Mic'], silent=True))
    request = FakeControlRequest(
        gui_protocol.SetTrackNames(
            type='set_track_names', track_names={'Mic': {'Lead Vocal': 0}}
        )
    )
    rec.live = FakeControlDisplay([request])

    rec._receive_control_requests()

    assert request.responses == [
        gui_protocol.Error(
            type='error', message='track_names channel values must be positive'
        )
    ]


def test_control_request_sets_noise_floor(
    monkeypatch: pytest.MonkeyPatch,
    mock_devices: None,
) -> None:
    monkeypatch.setattr(recorder, 'DevicePoller', FakePoller)
    monkeypatch.setattr(recorder, 'SourceProcess', FakeSourceProcess)
    rec = Recorder(Cfg(include=['Mic'], silent=True))
    request = FakeControlRequest(
        gui_protocol.SetNoiseFloor(
            type='set_noise_floor', source='Mic', channel=1, noise_floor=42.5
        )
    )
    rec.live = FakeControlDisplay([request])

    rec._receive_control_requests()

    assert rec.cfg.recording.channel_noise_floors == {'Mic': {'1': 42.5}}
    assert request.responses == [
        gui_protocol.NoiseFloorSet(
            type='noise_floor_set', source='Mic', channel=1, noise_floor=42.5
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

    assert Path('sessions/2026-06-23/recs-session.jsonl').exists()


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
    expected = recorder._session_directory_name(timestamp)
    path = Path(rec.cfg.directory.output_directory) / 'mic.wav'
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

    assert rec.cfg.directory.output_directory == expected
    assert (path.parent / 'recs-session.jsonl').exists()


def test_default_output_directory_uses_collision_suffix(
    monkeypatch: pytest.MonkeyPatch,
    mock_devices: None,
    tmp_path: Path,
) -> None:
    timestamp = datetime(2026, 6, 23, 20, 34, 10).timestamp()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(recorder.times, 'timestamp', lambda: timestamp)
    monkeypatch.setattr(recorder, 'SourceProcess', FakeSourceProcess)
    expected = recorder._session_directory_name(timestamp)
    Path(expected).mkdir()

    rec = Recorder(Cfg(include=['Mic'], silent=True))

    assert rec.cfg.directory.output_directory == f'{expected}_1'


def test_daemon_default_output_directory_uses_largest_external_disk(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    small = tmp_path / 'small'
    large = tmp_path / 'large'
    monkeypatch.setattr(recorder.gui_ipc, 'daemon_mode_enabled', lambda: True)
    monkeypatch.setattr(recorder, '_mounted_record_disks', lambda: [small, large])
    monkeypatch.setattr(
        recorder.shutil,
        'disk_usage',
        lambda p: DiskUsage(100, 50, 10 if p == small else 90),
    )

    timestamp = datetime(2026, 6, 23, 20, 34, 10).timestamp()
    cfg = recorder._with_default_output_directory(
        Cfg(default_record_directory='takes'), timestamp
    )

    assert cfg.directory.output_directory == str(
        large / 'takes' / '2026-06-23 20:34:10'
    )


def test_daemon_default_output_directory_falls_back_to_system_disk(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(recorder.gui_ipc, 'daemon_mode_enabled', lambda: True)
    monkeypatch.setattr(recorder, '_mounted_record_disks', lambda: [])
    monkeypatch.setattr(recorder.Path, 'home', lambda: tmp_path)

    timestamp = datetime(2026, 6, 23, 20, 34, 10).timestamp()
    cfg = recorder._with_default_output_directory(Cfg(), timestamp)

    assert cfg.directory.output_directory == str(
        tmp_path / 'recs' / '2026-06-23 20:34:10'
    )


def test_daemon_default_output_directory_keeps_explicit_directory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(recorder.gui_ipc, 'daemon_mode_enabled', lambda: True)

    cfg = recorder._with_default_output_directory(Cfg(output_directory='manual'), 0)

    assert cfg.directory.output_directory == 'manual'


def test_windows_default_output_directory_avoids_colons(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    timestamp = datetime(2026, 6, 23, 20, 34, 10).timestamp()

    monkeypatch.setattr(recorder.os, 'name', 'nt')

    assert recorder._session_directory_name(timestamp) == 'recs 2026-06-23 20-34-10'


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
    rec.poller.snapshots = [{'Mic': mic_info}, {}, {'Mic': mic_info}]

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
    records = read_jsonl(tmp_path / 'recs-session.jsonl')
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
    records = read_jsonl(tmp_path / 'recs-session.jsonl')
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
