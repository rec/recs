import pytest

from recs.base.errors import RecsError
from recs.cfg import settings
from recs.cfg.cfg import Cfg
from recs.cfg.device import InputDevice
from recs.cfg.track import Track
from recs.cfg.track_names import SourceTrackNames
from recs.daemon import gui_protocol
from recs.musicians import Musician, SourceMusician
from recs.recording.session_record import Record
from recs.runtime import recording_track_config
from test.conftest import DEVICES


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
        self.cfg = Cfg(save_settings=False, **cfg.model_dump())
        self.devices = FakeDevices(source)
        self.state = FakeState()
        self.track_names: SourceTrackNames = {}
        self.saved_tracks: dict[str, list[settings.TrackSettings]] = {}
        self.musicians: dict[str, Musician] = {}
        self.channel_musicians: dict[str, SourceMusician] = {}
        self.records: list[Record] = []
        self.cfg_revision = 0
        self.cfgs: list[Cfg] = []
        self.project_name: str | None = None

    def write_entry(self, record: Record) -> None:
        self.records.append(record)

    def cfg_changed(self, cfg: Cfg) -> None:
        self.cfgs.append(cfg)


def test_musician_assignment_requires_one_musician_per_source() -> None:
    source = source_process(['1', '2'])
    control = FakeControl(Cfg(silent=True), source)
    mike = Musician(
        nickname='mike',
        names=['Michael'],
        public_keys=['ssh-ed25519 AAA'],
        links=['insta:mike', 'mailto:mike@example.com'],
    )
    control.musicians[mike.nickname] = mike
    control.musicians['sara'] = Musician(nickname='sara')

    assigned = recording_track_config.assign_musician(
        control,
        gui_protocol.AssignMusician(
            type='assign_musician', nickname='mike', source='Ext', channels=[1]
        ),
    )

    assert assigned.assignment == SourceMusician(musician='mike', channels=[1])
    assert control.track_names == {'Ext': {'1 + mike': 1}}
    with pytest.raises(RecsError, match='already assigned to mike'):
        recording_track_config.assign_musician(
            control,
            gui_protocol.AssignMusician(
                type='assign_musician', nickname='sara', source='Ext', channels=[2]
            ),
        )

    removed = recording_track_config.remove_musician(
        control,
        gui_protocol.RemoveMusician(
            type='remove_musician', nickname='mike', source='Ext', channels=[1]
        ),
    )

    assert removed.channels == [1]
    assert control.channel_musicians == {}
    assert [record.type for record in control.records] == [
        'musician_assigned',
        'musician_removed_from_channels',
    ]


def test_musician_list_returns_records_by_short_name() -> None:
    control = FakeControl(Cfg(silent=True), source_process(['1']))
    control.musicians = {
        'sara': Musician(nickname='sara'),
        'mike': Musician(nickname='mike', links=['insta:mike']),
    }

    response = recording_track_config.list_musicians(control)

    assert response == gui_protocol.Musicians(
        type='musicians',
        musicians={
            'mike': control.musicians['mike'],
            'sara': control.musicians['sara'],
        },
    )


def test_musician_edit_and_delete_update_assignments() -> None:
    source = source_process(['1'])
    control = FakeControl(Cfg(silent=True), source)
    control.musicians['mike'] = Musician(
        nickname='mike', names=['Michael'], links=['insta:mike']
    )
    control.channel_musicians['Ext'] = SourceMusician(musician='mike', channels=[1])

    updated = recording_track_config.edit_musician(
        control,
        gui_protocol.EditMusician(
            type='edit_musician', nickname='mike', public_keys=['ssh-ed25519 AAA']
        ),
    )
    deleted = recording_track_config.delete_musician(
        control,
        gui_protocol.DeleteMusician(type='delete_musician', nickname='mike'),
    )

    assert updated.musician.names == ['Michael']
    assert updated.musician.public_keys == ['ssh-ed25519 AAA']
    assert deleted.nickname == 'mike'
    assert control.musicians == {}
    assert control.channel_musicians == {}


def test_musician_assignment_names_a_complete_stereo_track() -> None:
    source = source_process(['1-2'])
    control = FakeControl(Cfg(silent=True), source)
    control.musicians['tom'] = Musician(nickname='tom')

    recording_track_config.assign_musician(
        control,
        gui_protocol.AssignMusician(
            type='assign_musician',
            nickname='tom',
            source='Ext',
            channels=[1, 2],
        ),
    )

    assert control.track_names == {'Ext': {'1-2 + tom': 1}}


def test_musician_assignment_can_leave_or_replace_a_track_label() -> None:
    source = source_process(['1'])
    control = FakeControl(Cfg(silent=True), source)
    control.musicians['tom'] = Musician(nickname='tom')
    control.track_names = {'Ext': {'Existing': 1}}

    recording_track_config.assign_musician(
        control,
        gui_protocol.AssignMusician(
            type='assign_musician',
            nickname='tom',
            source='Ext',
            channels=[1],
            track_name=False,
        ),
    )

    assert control.track_names == {'Ext': {'Existing': 1}}

    recording_track_config.assign_musician(
        control,
        gui_protocol.AssignMusician(
            type='assign_musician',
            nickname='tom',
            source='Ext',
            channels=[1],
            track_name='guitar',
        ),
    )

    assert control.track_names == {'Ext': {'1 + guitar': 1}}


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
