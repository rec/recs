from pathlib import Path

import pytest
from reccy.protocol import rpc

from recs.base.errors import RecsError
from recs.base.state import ChannelState
from recs.cfg import settings
from recs.cfg.cfg import Cfg
from recs.cfg.track import Track
from recs.daemon import external_ipc, gui_protocol
from recs.musicians import Musician, SourceMusician
from recs.recording.session_record import MarkerPosition, read
from recs.runtime import (
    disk_space_controller,
    recorder,
    recording_track_config,
)
from recs.runtime.recorder import Recorder
from recs.runtime.source_messages import SourceUpdate
from test.conftest import DEVICES
from test.runtime.recorder.fakes import (
    DiskUsage,
    FakeControlDisplay,
    FakeControlRequest,
    FakePoller,
    FakeSourceProcess,
    _raise_recs_error,
    read_jsonl,
    record_path,
)


def test_recorder_rejects_an_active_settings_writer(
    monkeypatch: pytest.MonkeyPatch,
    mock_devices: None,
) -> None:
    monkeypatch.setattr(recorder, 'SourceProcess', FakeSourceProcess)
    rec = Recorder(Cfg(save_settings=True, silent=True))
    writer = recorder.instances.InstanceDescriptor(
        identity=recorder.instances.InstanceIdentity(
            pid=999,
            start_token='writer',
            started_at=1,
            role='local',
        ),
        control_endpoint='/tmp/writer.sock',
        event_endpoint='/tmp/writer-events.sock',
        protocol_version=11,
        settings_path=rec.settings_path,
    )
    monkeypatch.setattr(
        recorder.instances,
        'claim_settings',
        lambda path, identity: _raise_recs_error(
            f'Recs PID {writer.identity.pid} is already saving {path}'
        ),
    )

    with pytest.raises(RecsError, match='Recs PID 999 is already saving'):
        rec.start()


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


def test_external_waveform_subscription_enables_source_updates(
    monkeypatch: pytest.MonkeyPatch,
    mock_devices: None,
) -> None:
    class External:
        def __init__(self) -> None:
            self.requests = [
                external_ipc.ControlRequest(rpc.Request(command='subscribe_waveforms'))
            ]
            self.responses: list[rpc.Result] = []
            self.subscription_changes: list[bool] = []

        def take_requests(self) -> list[external_ipc.ControlRequest]:
            return self.requests

        def set_waveform_subscription(
            self, active: bool, cfg: Cfg
        ) -> gui_protocol.WaveformSubscription:
            self.subscription_changes.append(active)
            return gui_protocol.WaveformSubscription(
                type='waveform_subscription',
                active=active,
                bucket_milliseconds=cfg.console.waveform_bucket_milliseconds,
                batch_milliseconds=cfg.console.waveform_batch_milliseconds,
            )

        def respond(
            self, request: external_ipc.ControlRequest, response: rpc.Result
        ) -> None:
            self.responses.append(response)

    monkeypatch.setattr(recorder, 'SourceProcess', FakeSourceProcess)
    rec = Recorder(Cfg(silent=True))
    external = External()
    rec.external = external

    rec._receive_control_requests()
    external.requests = [
        external_ipc.ControlRequest(rpc.Request(command='unsubscribe_waveforms'))
    ]
    rec._receive_control_requests()

    assert external.subscription_changes == [True, False]
    assert not rec._devices.waveforms_enabled
    assert external.responses == [
        {
            'type': 'waveform_subscription',
            'active': True,
            'bucket_milliseconds': 20,
            'batch_milliseconds': 100,
        },
        {
            'type': 'waveform_subscription',
            'active': False,
            'bucket_milliseconds': 20,
            'batch_milliseconds': 100,
        },
    ]


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
    assert response.version == 11
    assert response.instance == rec.instance
    assert 'status_snapshot' in response.commands
    assert 'subscribe_waveforms' in response.commands
    assert 'unsubscribe_waveforms' in response.commands
    assert 'new_session' in response.commands
    assert 'shutdown' in response.commands
    assert 'add_musician' in response.commands
    assert 'list_musicians' in response.commands
    assert 'edit_musician' in response.commands
    assert 'delete_musician' in response.commands
    assert 'assign_musician' in response.commands
    assert 'remove_musician' in response.commands


def test_control_request_marks_record(
    monkeypatch: pytest.MonkeyPatch,
    mock_devices: None,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(recorder, 'DevicePoller', FakePoller)
    monkeypatch.setattr(recorder, 'SourceProcess', FakeSourceProcess)
    rec = Recorder(Cfg(include=['Mic'], output_directory=str(tmp_path), silent=True))
    request = FakeControlRequest(gui_protocol.Mark(type='mark', label='guitar solo'))
    rec.live = FakeControlDisplay([request])
    rec._start_record()

    rec._receive_control_requests()

    records = read_jsonl(record_path(rec))
    assert request.responses == [
        gui_protocol.Marked(type='marked', label='guitar solo')
    ]
    assert records[1] == {
        'type': 'mark',
        'timestamp': records[1]['timestamp'],
        'label': 'guitar solo',
    }


def test_marks_keep_source_boundaries_but_not_paused_or_restarted_positions(
    monkeypatch: pytest.MonkeyPatch,
    mock_devices: None,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(recorder, 'DevicePoller', FakePoller)
    monkeypatch.setattr(recorder, 'SourceProcess', FakeSourceProcess)
    rec = Recorder(Cfg(include=['Mic'], output_directory=str(tmp_path), silent=True))
    rec._start_record()
    source = rec._devices.sources['Mic']
    source.start()
    position = MarkerPosition(
        source='Mic',
        clock_id='clock-first',
        frame=96_000,
        sample_rate=48_000,
        observed_at='2026-09-16T12:00:00Z',
    )
    rec._devices.receive_message(
        SourceUpdate(
            channels={}, files=[], frames=0, source_name='Mic', marker_position=position
        )
    )
    rec._control.mark(gui_protocol.Mark(type='mark', label='anchored'))
    rec._control.recording_paused = True
    rec._control.mark(gui_protocol.Mark(type='mark', label='paused'))
    rec._control.recording_paused = False
    source.stop()
    source.start()
    rec._control.mark(gui_protocol.Mark(type='mark', label='restarted'))
    marks = [e for e in read(record_path(rec)).events if e.type == 'mark']
    assert marks[0].positions == [position]
    assert marks[1].positions is None
    assert marks[2].positions is None


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


def test_explicit_resume_closes_playback_before_resuming_capture(
    monkeypatch: pytest.MonkeyPatch, mock_devices: None, tmp_path: Path
) -> None:
    monkeypatch.setattr(recorder, 'DevicePoller', FakePoller)
    monkeypatch.setattr(recorder, 'SourceProcess', FakeSourceProcess)
    rec = Recorder(Cfg(include=['Mic'], output_directory=str(tmp_path), silent=True))
    rec._start_record()
    rec._control.pause_recording('playback')
    rec._playback.resume_after_playback = True
    stopped: list[bool] = []

    class Runner:
        def stop(self) -> None:
            stopped.append(rec._control.recording_paused)

    rec._playback.runner = Runner()
    rec._control.resume_recording('resume_recording')

    assert stopped == [True]
    assert rec._playback.runner is None
    assert not rec._control.recording_paused
    assert [r['type'] for r in read_jsonl(record_path(rec))].count(
        'recording_resumed'
    ) == 1


def test_manual_pause_during_playback_prevents_automatic_resume(
    monkeypatch: pytest.MonkeyPatch, mock_devices: None, tmp_path: Path
) -> None:
    monkeypatch.setattr(recorder, 'DevicePoller', FakePoller)
    monkeypatch.setattr(recorder, 'SourceProcess', FakeSourceProcess)
    rec = Recorder(Cfg(include=['Mic'], output_directory=str(tmp_path), silent=True))
    rec._start_record()
    rec._control.pause_recording('playback')
    rec._playback.resume_after_playback = True

    class Runner:
        def stop(self) -> None:
            pass

    rec._playback.runner = Runner()

    rec._control.pause_recording('pause_recording')
    rec._playback.stop()

    assert not rec._playback.resume_after_playback
    assert rec._control.recording_paused


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
    repeated_pause = FakeControlRequest(
        gui_protocol.PauseRecording(type='pause_recording')
    )
    resume = FakeControlRequest(gui_protocol.ResumeRecording(type='resume_recording'))
    rec.live = FakeControlDisplay([pause, repeated_pause, resume])
    rec._start_record()

    rec._receive_control_requests()

    assert not rec._control.recording_paused
    assert pause.responses == [
        gui_protocol.RecordingState(
            type='recording_state', paused=True, was_paused=False
        )
    ]
    assert repeated_pause.responses == [
        gui_protocol.RecordingState(
            type='recording_state', paused=True, was_paused=True
        )
    ]
    assert not rec._devices.hardware['Mic'].running
    assert not rec._devices.hardware['Mic'].started
    assert rec._devices.hardware['Mic'].stop_count == 1
    assert rec._devices.hardware['Mic'].join_count == 1
    records = read_jsonl(record_path(rec))
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
    rec._start_record()

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
    records = read_jsonl(record_path(rec))
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
    rec._start_record()

    rec._receive_update(
        SourceUpdate(
            channels={'1': ChannelState()},
            files=[],
            frames=0,
            source_name='Mic',
            config_revisions_applied=[3],
        )
    )

    records = read_jsonl(record_path(rec))
    assert records[1]['type'] == 'cfg_applied'
    assert records[1]['source'] == 'Mic'
    assert records[1]['value'] == 3


def test_save_settings_failure_records_warning(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    records: list[object] = []
    control = object.__new__(recorder.recording_control.RecordingControl)
    control.cfg = Cfg(save_settings=True)
    control.track_names = {}
    control.saved_tracks = {}
    control.musicians = {}
    control.channel_musicians = {}
    control.settings_profile = None
    control.write_entry = records.append
    monkeypatch.setattr(
        recording_track_config.settings,
        'save',
        lambda cfg, track_names, tracks, profile, **kwargs: _raise_recs_error(
            'cannot save settings'
        ),
    )

    recording_track_config.save_settings(control)

    assert records[0].message == 'cannot save settings'


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


def test_recorder_snapshots_and_records_musician_assignments(
    monkeypatch: pytest.MonkeyPatch,
    mock_devices: None,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(recorder, 'DevicePoller', FakePoller)
    monkeypatch.setattr(recorder, 'SourceProcess', FakeSourceProcess)
    musicians = {'mike': Musician(name='mike', contacts=['insta:mike'])}
    assignments = {'Mic': SourceMusician(musician='mike', channels=[1])}
    rec = Recorder(
        Cfg(include=['Mic'], output_directory=str(tmp_path), silent=True),
        settings.LoadedSettings(
            cfg=Cfg(include=['Mic'], output_directory=str(tmp_path), silent=True),
            musicians=musicians,
            channel_musicians=assignments,
        ),
    )
    rec._start_record()
    request = FakeControlRequest(
        gui_protocol.RemoveMusician(type='remove_musician', name='mike')
    )
    rec.live = FakeControlDisplay([request])

    rec._receive_control_requests()

    assert read(record_path(rec)).channel_musicians == assignments
    assert request.responses == [
        gui_protocol.MusicianAssignmentRemoved(type='musician_assignment_removed')
    ]
    assert read(record_path(rec)).events[-1].type == 'musician_removed_from_channels'


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
                'Immutable configuration attribute: recording.memory_reserve_megabytes'
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
    source = rec._devices.sources['Mic']
    source.start()
    profiles.write_text('{"Mic": {"noise_floor": 51}}')
    request = FakeControlRequest(gui_protocol.ReloadProfiles(type='reload_profiles'))
    rec.live = FakeControlDisplay([request])

    rec._receive_control_requests()

    assert request.responses == [
        gui_protocol.ProfilesReloaded(
            type='profiles_reloaded', profiles_path=str(profiles)
        )
    ]
    assert source.cfg.with_device_profile('Mic').recording.noise_floor == 51
    assert source.cfg_revision == 1
    assert source.start_count == 1
    assert source.stop_count == 0


@pytest.mark.parametrize(
    ('replacement', 'message'),
    [
        ('{', 'Expecting property name'),
        (
            '{"Mic": {"noise_floor": 51, "formats": ["flac"]}, '
            '"Offline": {"unknown": true}}',
            'Unknown profile field',
        ),
        (
            '{"Mic": {"noise_floor": 51, "formats": ["wav"]}}',
            'startup-only setting changed: audio.formats',
        ),
        (
            '{"Other": {"noise_floor": 51}}',
            'startup-only setting changed: audio.formats',
        ),
    ],
)
def test_rejected_profile_reload_preserves_all_active_configuration(
    monkeypatch: pytest.MonkeyPatch,
    mock_devices: None,
    tmp_path: Path,
    replacement: str,
    message: str,
) -> None:
    profiles = tmp_path / 'profiles.json'
    profiles.write_text('{"Mic": {"noise_floor": 42, "formats": ["flac"]}}')
    monkeypatch.setattr(recorder, 'DevicePoller', FakePoller)
    monkeypatch.setattr(recorder, 'SourceProcess', FakeSourceProcess)
    # A removed startup override must also be rejected, even when its old value
    # differs from the global default rather than appearing in the new file.
    rec = Recorder(
        Cfg(
            profiles=profiles,
            formats=['wav'],
            subtype='pcm_24',
            include=['Mic'],
            silent=True,
        )
    )
    source = rec._devices.sources['Mic']
    source.start()
    previous = rec.cfg
    source_cfg = source.cfg
    profiles.write_text(replacement)
    request = FakeControlRequest(gui_protocol.ReloadProfiles(type='reload_profiles'))
    rec.live = FakeControlDisplay([request])

    rec._receive_control_requests()

    assert len(request.responses) == 1
    assert isinstance(request.responses[0], gui_protocol.Error)
    assert message in request.responses[0].message
    assert rec.cfg is previous
    assert source.cfg is source_cfg
    assert source.cfg.with_device_profile('Mic').recording.noise_floor == 42
    assert rec._control.cfg_revision == 0
    assert source.start_count == 1
    assert source.stop_count == 0
