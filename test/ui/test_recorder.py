import json
import typing as t
from datetime import datetime
from pathlib import Path

import pytest
from threa import Runnable

from recs.base import RecsError
from recs.base.state import ChannelState
from recs.cfg import Cfg
from recs.cfg.track import Track
from recs.daemon.gui_protocol import Command
from recs.ui import recorder
from recs.ui.key_events import KeyEvent
from recs.ui.recorder import Recorder
from recs.ui.source_recorder import BufferStats, SourceFailure, SourceFile, SourceUpdate
from test.conftest import DEVICES, DEVICES_FILE


class DiskUsage(t.NamedTuple):
    total: int
    used: int
    free: int


class FakePoller(Runnable):
    def __init__(self, interval: float) -> None:
        self.snapshots: list[dict[str, t.Any] | None] = []

    def latest(self) -> dict[str, t.Any] | None:
        return self.snapshots.pop(0) if self.snapshots else None

    def poll(self) -> None:
        pass


def read_jsonl(path: Path) -> list[dict[str, t.Any]]:
    return [json.loads(line) for line in path.read_text().splitlines()]


class FakeConnection:
    def poll(self) -> bool:
        return False


class FakeSourceProcess:
    def __init__(self, cfg: Cfg, tracks: t.Sequence[Track]) -> None:
        self.name = tracks[0].source.name
        self.source = tracks[0].source
        self.connection = FakeConnection()
        self.started = False
        self.running = False
        self.alive = False
        self.start_count = 0
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

    def take_updates(self) -> list[SourceUpdate]:
        updates, self.pending_updates = self.pending_updates, []
        return updates


class ClosedDisplay(Runnable):
    enabled = True
    closed = True

    def __init__(
        self, rows: t.Callable[[], t.Iterator[t.Mapping[str, object]]], cfg: Cfg
    ) -> None:
        self.rows = rows
        self.cfg = cfg
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
    def __init__(self) -> None:
        self.command = Command(type='command', id='c1', command='calibrate')
        self.replies: list[dict[str, object]] = []

    def reply(
        self,
        *,
        ok: bool,
        result: dict[str, object] | None = None,
        message: str | None = None,
    ) -> None:
        reply = {'ok': ok}
        if result is not None:
            reply['result'] = result
        if message is not None:
            reply['message'] = message
        self.replies.append(reply)


def test_recorder_fails(mock_devices):
    with pytest.raises(RecsError) as e:
        Recorder(Cfg(include=['e'], exclude=['e']))
    assert e.value.args == ('No channels selected',)


def test_recorder_replaces_returning_device(
    monkeypatch: pytest.MonkeyPatch,
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
    rec.files_written.update((second, tmp_path / 'deleted.wav', first))
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
        recorder.sp,
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


def test_calibrate_control_request_writes_profile(
    monkeypatch: pytest.MonkeyPatch,
    mock_devices: None,
    tmp_path: Path,
) -> None:
    profiles = tmp_path / 'profiles.json'
    profiles.write_text('{"Mic": {"recording": {"quiet_after_end": 5}}}')
    monkeypatch.setattr(recorder, 'DevicePoller', FakePoller)
    monkeypatch.setattr(recorder, 'SourceProcess', FakeSourceProcess)
    rec = Recorder(
        Cfg(profiles=profiles, include=['Mic'], preview_headroom=9, silent=True)
    )
    request = FakeControlRequest()
    rec.live = FakeControlDisplay([request])
    rec.state.update({'Mic': {'1': ChannelState(max_amp=0.5, min_amp=-0.5)}})

    rec._receive_control_requests()

    assert json.loads(profiles.read_text()) == {
        'Mic': {'noise_floor': 15.0, 'recording': {'quiet_after_end': 5}}
    }
    assert all(source.cfg is rec.cfg for source in rec.sources.values())
    assert request.replies == [
        {
            'ok': True,
            'result': {
                'measurements': {
                    'Mic - 1': 6.020599913279624,
                    '(all)': 6.020599913279624,
                },
                'profiles': {'Mic': {'noise_floor': 15.0}},
                'profiles_path': str(profiles),
            },
        }
    ]


def test_calibrate_control_request_requires_profiles(
    monkeypatch: pytest.MonkeyPatch,
    mock_devices: None,
) -> None:
    monkeypatch.setattr(recorder, 'DevicePoller', FakePoller)
    monkeypatch.setattr(recorder, 'SourceProcess', FakeSourceProcess)
    rec = Recorder(Cfg(include=['Mic'], silent=True))
    request = FakeControlRequest()
    rec.live = FakeControlDisplay([request])

    rec._receive_control_requests()

    assert request.replies == [
        {
            'ok': False,
            'message': 'Cannot calibrate noise floor without --profiles',
        }
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
    rec.poller.snapshots = [{'Mic': mic_info}, {}]

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
    records = read_jsonl(tmp_path / 'recs-session.jsonl')
    assert records[1:] == [
        {
            'timestamp': '1970-01-01T00:01:43.000Z',
            'type': 'source_online',
            'source': 'Mic',
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
            'type': 'source_offline',
            'source': 'Mic',
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
