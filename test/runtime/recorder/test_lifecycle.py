from pathlib import Path
from typing import Any

import pytest
from reccy.protocol import rpc
from threa import Runnable

from recs.base.errors import ErrorRecord
from recs.cfg.cfg import Cfg
from recs.daemon import external_ipc
from recs.recording import recording_paths
from recs.runtime import (
    recorder,
)
from recs.runtime.recorder import Recorder
from test.conftest import DEVICES_FILE
from test.runtime.recorder.fakes import ClosedDisplay, FakePoller, FakeSourceProcess


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
