from .track import Track

SourceTrackNames = dict[str, dict[str, int]]


def validate_track_names(track_names: SourceTrackNames) -> SourceTrackNames:
    for source_key, names in track_names.items():
        if not source_key:
            raise ValueError('track_names source keys must not be empty')
        for name, channel in names.items():
            if not name:
                raise ValueError('track_names names must not be empty')
            if channel <= 0:
                raise ValueError('track_names channel values must be positive')
    return track_names


def track_name(track_names: SourceTrackNames, track: Track) -> str:
    names = track_names.get(track.source.key, {})
    for name, channel in names.items():
        if channel in track.channels:
            return name
    return ''
