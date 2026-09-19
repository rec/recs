from pathlib import Path

import pytest

from recs.base.errors import ErrorRecord, RecsError
from recs.base.state import ChannelState
from recs.cfg import device
from recs.cfg.cfg import Cfg
from recs.runtime import (
    recorder,
)
from recs.runtime.recorder import Recorder
from recs.runtime.source_messages import BufferStats, SourceFailure, SourceUpdate
from test.conftest import DEVICES, DEVICES_FILE
from test.runtime.recorder.fakes import ClosedDisplay, FakePoller, FakeSourceProcess


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


def test_recorder_waits_for_missing_included_devices(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ext_info = next(info for info in DEVICES if info['name'] == 'Ext')
    mic_info = next(info for info in DEVICES if info['name'] == 'Mic')
    monkeypatch.setattr(device, 'query_devices', lambda: [ext_info])
    monkeypatch.setattr(recorder, 'DevicePoller', FakePoller)
    monkeypatch.setattr(recorder, 'SourceProcess', FakeSourceProcess)

    rec = Recorder(Cfg(include=['Mic', 'XR18', 'Flow 8'], silent=True))

    assert rec._devices.hardware == {}
    assert rec.error_messages() == []

    assert rec._devices.poller is not None
    rec._devices.poller.snapshots = [{'Ext': ext_info, 'Mic': mic_info}]
    rec._poll_devices()

    assert list(rec._devices.hardware) == ['Mic']
    assert rec._devices.hardware['Mic'].started


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


def test_external_ipc_start_failure_stops_recorder_before_devices_open(
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

    with pytest.raises(RecsError, match='Cannot start Recs control server'):
        rec.start()

    assert external.closed


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


def test_unavailable_source_names_another_recs_instance(
    monkeypatch: pytest.MonkeyPatch,
    mock_devices: None,
) -> None:
    monkeypatch.setattr(recorder, 'SourceProcess', FakeSourceProcess)
    rec = Recorder(Cfg(devices=Path(DEVICES_FILE), include=['Mic'], silent=True))
    other = recorder.instances.InstanceDescriptor(
        identity=recorder.instances.InstanceIdentity(
            pid=999,
            start_token='other',
            started_at=1,
            role='local',
            profile='second-interface',
        ),
        control_endpoint='/tmp/other.sock',
        event_endpoint='/tmp/other-events.sock',
        protocol_version=10,
    )
    monkeypatch.setattr(
        recorder.instances,
        'source_users',
        lambda source, identity: [other],
    )

    rec._receive_source_message(
        SourceFailure(
            message='PortAudioError: device unavailable',
            source_name='Mic',
            device_unavailable=True,
        )
    )

    assert rec.error_records()[1].message == (
        'Device Mic is also selected by Recs PID 999 (local) with profile '
        "'second-interface'"
    )


def test_recorder_finishes_with_all_devices_offline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(recorder, 'DevicePoller', FakePoller)
    monkeypatch.setattr(recorder, 'SourceProcess', FakeSourceProcess)
    rec = Recorder(Cfg(devices=Path(DEVICES_FILE), silent=True, total_run_time=0.1))
    rec.state.start_time -= 1

    assert rec._done([])


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
