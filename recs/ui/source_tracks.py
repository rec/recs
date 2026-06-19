import typing as t

from recs.base import RecsError
from recs.cfg import Cfg, FileSource, Source, Track
from recs.cfg.track import source_track as _source_track


def source_tracks(cfg: Cfg) -> t.Iterator[tuple[Source, t.Sequence[Track]]]:
    if not (cfg.devices or cfg.files):
        raise RecsError('No inputs were found')

    if cfg.files:
        for file in cfg.files:
            source = FileSource(file)
            channels = '1' if source.channels == 1 else f'1-{source.channels}'
            track = Track(source, channels)
            yield source, [track]

    else:
        exc = cfg.aliases.to_tracks(cfg.exclude)
        inc = cfg.aliases.to_tracks(cfg.include)
        for d in cfg.devices.values():
            if tracks := list(_source_track(d, exc, inc)):
                yield d, tracks
