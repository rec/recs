from collections.abc import Iterator, Sequence

from recs.cfg.aliases import Aliases
from recs.cfg.cfg import Cfg
from recs.cfg.device import InputDevice, InputDevices
from recs.cfg.file_source import FileSource
from recs.cfg.source import Source
from recs.cfg.track import Track, source_track


def source_tracks(cfg: Cfg) -> Iterator[tuple[Source, Sequence[Track]]]:
    if cfg.directory.files:
        for file in cfg.directory.files:
            source = FileSource(file)
            channels = '1' if source.channels == 1 else f'1-{source.channels}'
            track = Track(source, channels)
            yield source, [track]

    else:
        yield from input_device_tracks(cfg, cfg.input_devices)


def input_device_tracks(
    cfg: Cfg,
    input_devices: InputDevices,
) -> Iterator[tuple[InputDevice, Sequence[Track]]]:
    if not input_devices:
        return

    aliases = Aliases(cfg.device.alias, input_devices)
    exc = aliases.to_tracks(cfg.selection.exclude)
    inc = aliases.to_tracks(cfg.selection.include)
    for d in input_devices.values():
        if tracks := list(source_track(d, exc, inc)):
            yield d, tracks
