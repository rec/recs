from collections.abc import Iterator
from pathlib import Path
from time import monotonic_ns

import pytest
from reccy.protocol import rpc

from recs.base.errors import RecsError
from recs.base.state import ChannelState
from recs.cfg import device, mic_mute
from recs.cfg.cfg import Cfg
from recs.daemon import external_ipc, gui_protocol
from recs.runtime import audio_forwarding, recorder
from recs.runtime.audio_source import AudioSource
from recs.runtime.recorder import Recorder
from recs.runtime.source_messages import SourceUpdate
from test.conftest import DEVICES, DEVICES_FILE
from test.runtime.recorder.fakes import FakePoller, FakeSourceProcess


@pytest.fixture
def capturing(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[Recorder]:
    monkeypatch.setattr(recorder.times, 'timestamp', lambda: 100.0)
    monkeypatch.setattr(device, 'query_devices', lambda: DEVICES)
    monkeypatch.setattr(recorder, 'DevicePoller', FakePoller)
    monkeypatch.setattr(recorder, 'SourceProcess', FakeSourceProcess)
    rec = Recorder(
        Cfg(
            devices=DEVICES_FILE,
            include=['Flower 8'],
            forward_audio=True,
            output_directory=str(tmp_path),
            silent=True,
        )
    )
    rec._devices.poller.snapshots = [DEVICES]
    rec._poll_devices()
    source = rec._devices.hardware['Flower 8']
    source.audio = AudioSource(
        source.name, source.source.samplerate, source.source.channels
    )
    rec._receive_update(
        SourceUpdate(
            channels={source.tracks[0].name: ChannelState()},
            files=[],
            frames=48_000,
            source_name=source.name,
        )
    )
    try:
        yield rec
    finally:
        source.audio.close()


def test_control_negotiates_and_cancels_exact_instance_source_channels(
    capturing: Recorder,
) -> None:
    rec = capturing
    raw = rpc.Request(
        command='subscribe_audio', params={'source': 'Flower 8', 'channels': [2, 1]}
    )
    result = rec._control.protocol.handle(external_ipc.recs_request(raw))
    assert isinstance(result, gui_protocol.AudioSubscribed)
    assert result.instance == rec.instance
    assert result.subscription.channels == [2, 1]
    assert result.subscription.instance_token == rec.instance.start_token
    assert result.subscription.host == '127.0.0.1'
    assert external_ipc.response(raw, result)['subscription']['secret']
    status = rec._control.protocol.handle(
        gui_protocol.AudioStatusRequest(type='audio_status')
    )
    assert status.sources[0]['state'] == 'pending'
    assert status.sources[0]['recording_enabled']
    assert 'secret' not in status.model_dump_json()
    cancellation = rec._control.protocol.handle(
        gui_protocol.UnsubscribeAudio(
            type='unsubscribe_audio',
            source='Flower 8',
            subscription_id=result.subscription.subscription_id,
        )
    )
    assert cancellation.stopped
    assert rec._devices.hardware['Flower 8'].running
    assert rec._control.audio_status().sources[0]['state'] == 'idle'


@pytest.mark.parametrize(
    'condition',
    ['disabled', 'paused', 'muted', 'failed', 'stopped', 'stale', 'shutdown'],
)
def test_control_rejects_audio_when_not_allowed(
    capturing: Recorder, condition: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    rec = capturing
    source = rec._devices.hardware['Flower 8']
    if condition == 'disabled':
        rec._control.cfg = Cfg(forward_audio=False)
    elif condition == 'paused':
        rec._control.recording_paused = True
    elif condition == 'muted':
        mic_mute.save(mic_mute.MicMute(device_name='Flower 8', is_muted=True))
        rec._control.cfg = Cfg(forward_audio=True)
    elif condition == 'failed':
        rec._devices.failed.add(source.name)
    elif condition == 'stopped':
        source.running = False
    elif condition == 'stale':
        monkeypatch.setattr(recorder.times, 'timestamp', lambda: 111.0)
    else:
        rec._control.shutdown_started = True
    with pytest.raises(RecsError):
        rec._control.subscribe_audio(
            gui_protocol.SubscribeAudio(
                type='subscribe_audio', source='Flower 8', channels=[1, 2]
            )
        )
    assert source.audio.subscription is None


@pytest.mark.parametrize('channels', [[1, 1], [11]])
def test_control_rejects_bad_channel_selection_without_mutation(
    capturing: Recorder, channels: list[int]
) -> None:
    with pytest.raises(RecsError, match='physical channels'):
        capturing._control.subscribe_audio(
            gui_protocol.SubscribeAudio(
                type='subscribe_audio', source='Flower 8', channels=channels
            )
        )
    assert capturing._devices.hardware['Flower 8'].audio.subscription is None


@pytest.mark.parametrize('channels', [None, 2, 10])
def test_storage_suspension_preserves_forwarding_capture_but_still_detects_stall(
    capturing: Recorder,
    monkeypatch: pytest.MonkeyPatch,
    channels: int | None,
) -> None:
    rec = capturing
    source = rec._devices.hardware['Flower 8']
    rec._devices.set_writing_enabled(False)
    source.audio.counters[audio_forwarding.CAPTURE_FRAME] = 48_000
    source.audio.counters[audio_forwarding.CAPTURE_TIME] = monotonic_ns()
    monkeypatch.setattr(recorder.times, 'timestamp', lambda: 120.0)
    info = next(i for i in DEVICES if i['name'] == 'Flower 8')
    rec._devices.poller.snapshots = [
        [] if channels is None else [{**info, 'max_input_channels': channels}]
    ]
    rec._poll_devices()
    rec._stop_stalled_sources()
    assert source.running
    result = rec._control.subscribe_audio(
        gui_protocol.SubscribeAudio(
            type='subscribe_audio', source='Flower 8', channels=[1, 2]
        )
    )
    assert result.subscription.source == source.name
    assert not rec._control.audio_status().sources[0]['recording_enabled']
    source.audio.counters[audio_forwarding.CAPTURE_TIME] = (
        monotonic_ns() - 11_000_000_000
    )
    rec._stop_stalled_sources()
    assert not source.running
    assert source.name in rec._devices.failed


@pytest.mark.parametrize('action', ['pause', 'mute'])
def test_privacy_controls_revoke_pending_audio_without_waiting_for_discovery(
    capturing: Recorder, action: str
) -> None:
    rec = capturing
    source = rec._devices.hardware['Flower 8']
    result = rec._control.subscribe_audio(
        gui_protocol.SubscribeAudio(
            type='subscribe_audio', source=source.name, channels=[1]
        )
    )
    if action == 'pause':
        rec._control.pause_recording('pause_recording')
    else:
        mic_mute.save(mic_mute.MicMute(device_name='Flower 8', is_muted=True))
        rec._devices.set_cfg(Cfg(forward_audio=True))
    assert not source.audio.active
    assert source.audio.counters[audio_forwarding.DESIRED] == 0
    assert not source.running
    assert result.subscription.subscription_id


def test_resumed_writer_backlog_does_not_look_like_a_slow_device_clock(
    capturing: Recorder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rec = capturing
    source = rec._devices.hardware['Flower 8']
    rec._devices.set_writing_enabled(False)
    monkeypatch.setattr(recorder.times, 'timestamp', lambda: 130.0)
    source.audio.counters[audio_forwarding.CAPTURE_FRAME] = (
        30 * source.source.samplerate
    )
    source.audio.counters[audio_forwarding.CAPTURE_TIME] = monotonic_ns()
    rec._devices.set_writing_enabled(True)
    rec._receive_update(
        SourceUpdate(
            channels={source.tracks[0].name: ChannelState()},
            files=[],
            frames=960,
            source_name=source.name,
        )
    )
    assert source.running
    assert rec.error_messages() == []
    source.audio.counters[audio_forwarding.CAPTURE_FRAME] = source.source.samplerate
    rec._receive_update(
        SourceUpdate(
            channels={source.tracks[0].name: ChannelState()},
            files=[],
            frames=960,
            source_name=source.name,
        )
    )
    assert not source.running
    assert rec.error_messages() == ['Device Flower 8 lagging behind real time']
