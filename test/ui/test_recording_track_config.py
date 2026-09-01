from test.conftest import DEVICES

import pytest

from recs.base.errors import RecsError
from recs.cfg import settings
from recs.cfg.cfg import Cfg
from recs.cfg.device import InputDevice
from recs.cfg.track import Track
from recs.cfg.track_names import SourceTrackNames
from recs.daemon import gui_protocol
from recs.ui import recording_track_config
from recs.ui.session_record import RecordEntry


class FakeSourceProcess:
    def __init__(self, tracks: list[Track]) -> None:
        self.source = tracks[0].source
        self.name = self.source.key
        self.tracks = tracks
        self.track_names: SourceTrackNames = {}

    def set_tracks(self, tracks: list[Track], track_names: SourceTrackNames) -> None:
        self.tracks = tracks
        self.track_names = track_names


class FakeDevices:
    def __init__(self, source: FakeSourceProcess) -> None:
        self.hardware = {source.name: source}
        self.track_names: SourceTrackNames = {}
        self.cfg_updates: list[tuple[Cfg, int | None]] = []

    def set_track_names(self, track_names: SourceTrackNames) -> None:
        self.track_names = track_names

    def set_cfg(self, cfg: Cfg, revision: int | None = None) -> None:
        self.cfg_updates.append((cfg, revision))


class FakeState:
    def __init__(self) -> None:
        self.track_names: SourceTrackNames = {}

    def set_track_names(self, track_names: SourceTrackNames) -> None:
        self.track_names = track_names


class FakeControl:
    def __init__(self, cfg: Cfg, source: FakeSourceProcess) -> None:
        self.cfg = cfg
        self.devices = FakeDevices(source)
        self.state = FakeState()
        self.track_names: SourceTrackNames = {}
        self.saved_tracks: dict[str, list[settings.TrackSettings]] = {}
        self.records: list[RecordEntry] = []
        self.cfg_revision = 0
        self.cfgs: list[Cfg] = []

    def write_entry(self, record: RecordEntry) -> None:
        self.records.append(record)

    def cfg_changed(self, cfg: Cfg) -> None:
        self.cfgs.append(cfg)


def test_set_tracks_splits_stereo_track_and_records_event() -> None:
    source = source_process(['1-2', '3'])
    control = FakeControl(
        Cfg(channel_noise_floors={'Ext': {'1-2': 37}}, silent=True),
        source,
    )
    request = gui_protocol.SetTracks(
        type='set_tracks',
        source='Ext',
        tracks=[
            gui_protocol.ChannelTrack(channels=[1], name='VL'),
            gui_protocol.ChannelTrack(channels=[2]),
        ],
    )

    response = recording_track_config.set_tracks(control, request)

    assert response == gui_protocol.TracksSet(
        type='tracks_set', source='Ext', tracks=request.tracks
    )
    assert [track.name for track in source.tracks] == ['1', '2', '3']
    assert control.track_names == {'Ext': {'VL': 1}}
    assert source.track_names == {'Ext': {'VL': 1}}
    assert control.cfg.recording.channel_noise_floors == {'Ext': {'1': 37, '2': 37}}
    assert [record.type for record in control.records] == ['cfg_set', 'tracks_set']
    assert control.records[1].source == 'Ext'


def test_set_tracks_groups_mono_tracks_into_stereo_pair() -> None:
    source = source_process(['1', '2'])
    control = FakeControl(
        Cfg(channel_noise_floors={'Ext': {'1': 37, '2': 37}}, silent=True),
        source,
    )

    recording_track_config.set_tracks(
        control,
        gui_protocol.SetTracks(
            type='set_tracks',
            source='Ext',
            tracks=[gui_protocol.ChannelTrack(channels=[1, 2], name='Stereo')],
        ),
    )

    assert [track.name for track in source.tracks] == ['1-2']
    assert control.track_names == {'Ext': {'Stereo': 1}}
    assert control.cfg.recording.channel_noise_floors == {'Ext': {'1-2': 37}}


def test_set_tracks_rejects_partial_stereo_track_replacement() -> None:
    source = source_process(['1-2', '3'])
    control = FakeControl(Cfg(silent=True), source)

    with pytest.raises(
        RecsError, match='All channels in Ext \\+ 1-2 must be replaced together'
    ):
        recording_track_config.set_tracks(
            control,
            gui_protocol.SetTracks(
                type='set_tracks',
                source='Ext',
                tracks=[gui_protocol.ChannelTrack(channels=[1], name='VL')],
            ),
        )


def test_set_track_names_updates_devices_state_and_record() -> None:
    source = source_process(['1'])
    control = FakeControl(Cfg(silent=True), source)

    response = recording_track_config.set_track_names(
        control,
        gui_protocol.SetTrackNames(
            type='set_track_names', track_names={'Ext': {'Lead Vocal': 1}}
        ),
    )

    assert response == gui_protocol.TrackNames(
        type='track_names', track_names={'Ext': {'Lead Vocal': 1}}
    )
    assert control.track_names == {'Ext': {'Lead Vocal': 1}}
    assert control.devices.track_names == {'Ext': {'Lead Vocal': 1}}
    assert control.state.track_names == {'Ext': {'Lead Vocal': 1}}
    assert [record.type for record in control.records] == ['track_names_set']


def test_set_track_names_rejects_invalid_track_names() -> None:
    source = source_process(['1'])
    control = FakeControl(Cfg(silent=True), source)

    with pytest.raises(RecsError, match='track_names channel values must be positive'):
        recording_track_config.set_track_names(
            control,
            gui_protocol.SetTrackNames(
                type='set_track_names', track_names={'Ext': {'Lead Vocal': 0}}
            ),
        )


def test_set_noise_floor_updates_track_cfg() -> None:
    source = source_process(['1'])
    control = FakeControl(Cfg(silent=True), source)

    response = recording_track_config.set_noise_floor(
        control,
        gui_protocol.SetNoiseFloor(
            type='set_noise_floor', source='Ext', channel=1, noise_floor=42.5
        ),
    )

    assert response == gui_protocol.NoiseFloorSet(
        type='noise_floor_set', source='Ext', channel=1, noise_floor=42.5
    )
    assert control.cfg.recording.channel_noise_floors == {'Ext': {'1': 42.5}}
    assert [record.type for record in control.records] == ['cfg_set']


def source_process(channels: list[str]) -> FakeSourceProcess:
    source = InputDevice(DEVICES[0])
    return FakeSourceProcess([Track(source, channel) for channel in channels])
