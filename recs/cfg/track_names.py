from .track import Track

DeviceTrackNames = dict[str, dict[str, int]]


def validate_track_names(track_names: DeviceTrackNames) -> DeviceTrackNames:
    for device, names in track_names.items():
        if not device:
            raise ValueError('track_names device names must not be empty')
        for name, channel in names.items():
            if not name:
                raise ValueError('track_names names must not be empty')
            if channel <= 0:
                raise ValueError('track_names channel values must be positive')
    return track_names


def track_name(track_names: DeviceTrackNames, track: Track) -> str:
    names = track_names.get(track.source.name, {})
    for name, channel in names.items():
        if channel in track.channels:
            return name
    return ''
