import typing as t

from recs.base import RecsError
from recs.cfg import Cfg, FileSource, InputDevice, Source, Track


def device_tracks(cfg: Cfg) -> t.Iterator[tuple[Source, t.Sequence[Track]]]:
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
            if tracks := list(device_track(d, exc, inc)):
                yield d, tracks


def device_track(
    d: InputDevice, exc: t.Sequence[Track] = (), inc: t.Sequence[Track] = ()
) -> t.Iterator[Track]:
    if Track(d) in exc:
        return

    excs = [i for i in exc if d.name == i.source.name]
    incs = [i for i in inc if d.name == i.source.name]
    if inc and not incs:
        return

    tracks = [i for i in incs if i.channels]

    ic = {int(c) for t in tracks for c in t.channels} or set(range(1, d.channels + 1))
    ec = {int(c) for t in excs for c in t.channels}

    channels = sorted(ic - ec)

    def track_channel() -> int:
        return tracks[0].channels[-1]

    while channels:
        if tracks:
            found = False
            while channels and track_channel() >= channels[0]:
                channels.pop(0)
                found = True

            if found:
                yield tracks.pop(0)
                continue

            if not channels:
                break

        c1 = channels.pop(0)
        ch = f'{c1}'
        if (
            channels
            and channels[0] == c1 + 1
            and c1 % 2
            and not (tracks and track_channel() == c1 + 1)
        ):
            c2 = channels.pop(0)
            assert c1 + 1 == c2
            ch = f'{c1}-{c2}'

        yield Track(d, ch)

    yield from tracks
