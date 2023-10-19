import typing as t

from recs.audio import device

from .aliases import Aliases
from .track import Track


def device_tracks(
    aliases: t.Sequence[str] = (),
    exclude: t.Sequence[str] = (),
    include: t.Sequence[str] = (),
) -> t.Iterator[Track]:
    def channels(tracks: t.Sequence[Track]) -> set[int]:
        return {int(c) for t in tracks for c in t.channels}

    ali = Aliases(aliases)
    exc = ali.split_all(exclude)
    inc = ali.split_all(include)

    for d in device.input_devices().values():
        yield from device_track(d, exc, inc)


def device_track(
    d: device.InputDevice,
    exc: t.Sequence[Track] = (),
    inc: t.Sequence[Track] = (),
) -> t.Iterator[Track]:
    if Track(d.name) in exc:
        return

    excs = [i for i in exc if d.name == i.name]
    incs = [i for i in inc if d.name == i.name]
    if inc and not incs:
        return

    tracks = [i for i in incs if i.channel]

    ic = {int(c) for t in tracks for c in t.channels} or set(range(1, d.channels + 1))
    ec = {int(c) for t in excs for c in t.channels}

    channels = sorted(ic - ec)

    def track_channel() -> int:
        return tracks[0].channels[-1]

    while channels:
        while tracks and track_channel() < channels[0]:
            yield tracks.pop(0)

        if tracks:
            found = False
            while channels and track_channel() >= channels[0]:
                channels.pop(0)
                found = True

            if found:
                yield tracks.pop(0)

            if not channels:
                break

        c1 = channels.pop(0)
        ch = f'{c1}'
        if channels and c1 % 2 and channels[0] == c1 + 1:
            if not (tracks and track_channel() == c1 + 1):
                c2 = channels.pop(0)
                assert c1 + 1 == c2
                ch = f'{c1}-{c2}'

        yield Track(d.name, ch)

    yield from tracks
