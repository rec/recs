from typing import TYPE_CHECKING

from recs.base import times
from recs.base.errors import RecsError
from recs.cfg import settings
from recs.cfg.track import Track
from recs.cfg.track_names import SourceTrackNames, validate_track_names
from recs.daemon import gui_protocol

from .session_manifest import ManifestEvent, ManifestWarning, timestamp_to_json
from .source_process import SourceProcess

if TYPE_CHECKING:
    from .recording_control import RecordingControl


def set_key_label(
    control: 'RecordingControl', request: gui_protocol.SetKeyLabel
) -> gui_protocol.KeyLabelSet:
    labels = control.cfg.keys.labels | {request.key: request.label}
    set_cfg_value(
        control,
        'keys.key_label',
        [f'{key}={label}' for key, label in labels.items()],
    )
    return gui_protocol.KeyLabelSet(
        type='key_label_set', key=request.key, label=request.label
    )


def set_noise_floor(
    control: 'RecordingControl', request: gui_protocol.SetNoiseFloor
) -> gui_protocol.NoiseFloorSet:
    track = track_for_channel(control, request.source, request.channel)
    floors = {
        source: dict(channels)
        for source, channels in control.cfg.recording.channel_noise_floors.items()
    }
    floors.setdefault(request.source, {})[track.name] = request.noise_floor
    set_cfg_value(control, 'recording.channel_noise_floors', floors)
    return gui_protocol.NoiseFloorSet(
        type='noise_floor_set',
        source=request.source,
        channel=request.channel,
        noise_floor=request.noise_floor,
    )


def set_track_names(
    control: 'RecordingControl', request: gui_protocol.SetTrackNames
) -> gui_protocol.TrackNames:
    try:
        track_names = validate_track_names(request.track_names)
    except ValueError as e:
        raise RecsError(str(e)) from None
    control.track_names = {
        source_key: dict(names) for source_key, names in track_names.items()
    }
    control.devices.set_track_names(control.track_names)
    control.state.set_track_names(control.track_names)
    control.write_record(
        ManifestEvent(
            timestamp=timestamp_to_json(times.timestamp()),
            type='track_names_set',
            value=control.track_names,
        )
    )
    save_settings(control)
    return gui_protocol.TrackNames(type='track_names', track_names=control.track_names)


def set_tracks(
    control: 'RecordingControl', request: gui_protocol.SetTracks
) -> gui_protocol.TracksSet:
    source = control.hardware.get(request.source)
    if source is None:
        raise RecsError(f'Unknown input device: {request.source}')
    tracks = updated_tracks(source, request.tracks)
    names = updated_track_names(control, request.source, request.tracks)
    floors = updated_track_noise_floors(control, source, request.tracks)
    if floors != control.cfg.recording.channel_noise_floors:
        set_cfg_value(control, 'recording.channel_noise_floors', floors, save=False)
    control.track_names = names
    source.set_tracks(tracks, names)
    control.saved_tracks[source.name] = [
        settings.TrackSettings(channels=list(track.channels)) for track in tracks
    ]
    control.write_record(
        ManifestEvent(
            timestamp=timestamp_to_json(times.timestamp()),
            type='tracks_set',
            source=request.source,
            value=[track.model_dump() for track in request.tracks],
        )
    )
    save_settings(control)
    return gui_protocol.TracksSet(
        type='tracks_set', source=request.source, tracks=request.tracks
    )


def updated_tracks(
    source: SourceProcess,
    requested: list[gui_protocol.ChannelTrack],
) -> list[Track]:
    if not requested:
        raise RecsError('At least one track is required')
    channels: list[int] = []
    new_tracks: list[Track] = []
    for definition in requested:
        values = definition.channels
        if len(values) not in (1, 2):
            raise RecsError('Tracks must be mono or stereo')
        if values != sorted(values) or len(set(values)) != len(values):
            raise RecsError('Track channels must be in ascending order')
        if len(values) == 2 and values[1] != values[0] + 1:
            raise RecsError('Stereo channels must be adjacent')
        if values[0] <= 0 or values[-1] > source.source.channels:
            raise RecsError(f'Invalid channel for device {source.name}')
        try:
            track = Track(source.source, tuple(values))
        except RecsError as e:
            raise RecsError(str(e)) from None
        channels.extend(values)
        new_tracks.append(track)

    if len(channels) != len(set(channels)):
        raise RecsError('Tracks cannot share channels')
    selected = set(channels)
    for track in source.tracks:
        overlap = selected & set(track.channels)
        if overlap and overlap != set(track.channels):
            raise RecsError(f'All channels in {track} must be replaced together')
    remaining = [
        track for track in source.tracks if not (selected & set(track.channels))
    ]
    return sorted([*remaining, *new_tracks], key=lambda track: track.channels)


def updated_track_names(
    control: 'RecordingControl',
    source_key: str,
    requested: list[gui_protocol.ChannelTrack],
) -> SourceTrackNames:
    names = {
        source_key: dict(values) for source_key, values in control.track_names.items()
    }
    changed = {channel for track in requested for channel in track.channels}
    source_names = names.setdefault(source_key, {})
    for name, channel in list(source_names.items()):
        if channel in changed:
            del source_names[name]
    for track in requested:
        if not track.name:
            continue
        if track.name in source_names:
            raise RecsError(f'Duplicate track name: {track.name}')
        source_names[track.name] = track.channels[0]
    if not source_names:
        del names[source_key]
    try:
        return validate_track_names(names)
    except ValueError as e:
        raise RecsError(str(e)) from None


def updated_track_noise_floors(
    control: 'RecordingControl',
    source: SourceProcess,
    requested: list[gui_protocol.ChannelTrack],
) -> dict[str, dict[str, float | None]]:
    floors = {
        source_key: dict(values)
        for source_key, values in control.cfg.recording.channel_noise_floors.items()
    }
    source_floors = floors.setdefault(source.name, {})
    changed = {channel for track in requested for channel in track.channels}
    replaced = [track for track in source.tracks if changed & set(track.channels)]
    values = {track.name: source_floors.pop(track.name, None) for track in replaced}
    for definition in requested:
        matching = [
            value
            for track, value in values.items()
            if set(track_channels(track)) & set(definition.channels)
        ]
        if len(set(matching)) > 1:
            raise RecsError(
                'Cannot pair channels with different noise floors: '
                f'{definition.channels}'
            )
        if matching:
            source_floors[track_name(definition.channels)] = matching[0]
    if not source_floors:
        del floors[source.name]
    return floors


def get_cfg(
    control: 'RecordingControl', request: gui_protocol.GetCfg
) -> gui_protocol.CfgValue:
    try:
        value = control.cfg.get_attr(request.address)
    except ValueError as e:
        raise RecsError(str(e)) from None
    control.write_record(
        ManifestEvent(
            timestamp=timestamp_to_json(times.timestamp()),
            type='cfg_get',
            address=request.address,
            value=value,
        )
    )
    return gui_protocol.CfgValue(type='cfg_value', address=request.address, value=value)


def set_cfg(
    control: 'RecordingControl', request: gui_protocol.SetCfg
) -> gui_protocol.CfgSet:
    value = set_cfg_value(control, request.address, request.value)
    return gui_protocol.CfgSet(type='cfg_set', address=request.address, value=value)


def set_cfg_value(
    control: 'RecordingControl', address: str, value: object, *, save: bool = True
) -> object:
    try:
        control.cfg = control.cfg.set_attr(address, value)
    except ValueError as e:
        raise RecsError(str(e)) from None
    value = control.cfg.get_attr(address)
    control.cfg_revision += 1
    revision = control.cfg_revision
    control.devices.set_cfg(control.cfg, revision=revision)
    control.cfg_changed(control.cfg)
    control.write_record(
        ManifestEvent(
            timestamp=timestamp_to_json(times.timestamp()),
            type='cfg_set',
            address=address,
            value=value,
            cfg_revision=revision,
        )
    )
    if save:
        save_settings(control)
    return value


def save_settings(control: 'RecordingControl') -> None:
    if control.cfg.save_settings:
        try:
            settings.save(control.cfg, control.track_names, control.saved_tracks)
        except RecsError as e:
            control.write_record(
                ManifestWarning(
                    timestamp=timestamp_to_json(times.timestamp()),
                    message=str(e),
                )
            )


def track_for_channel(
    control: 'RecordingControl', source_name: str, channel: int
) -> Track:
    source = control.hardware.get(source_name)
    if source is None:
        raise RecsError(f'Unknown input device: {source_name}')
    if channel <= 0:
        raise RecsError('Channel must be positive')
    for track in source.tracks:
        if channel in track.channels:
            return track
    raise RecsError(f'Device {source_name} has no selected channel {channel}')


def track_channels(track_name: str) -> list[int]:
    return [int(channel) for channel in track_name.split('-') if channel]


def track_name(channels: list[int]) -> str:
    return '-'.join(str(channel) for channel in channels)
