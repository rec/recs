"""SFZ file acquisition; all format interpretation lives in Ufor."""

from pathlib import Path

from ufor import sfz
from ufor.time import Rate, Timebase

from .assets import read_audio_metadata


def read(
    path: Path, output_rate: int = 48_000, output_channels: list[str] | None = None
) -> sfz.SfzReadResult:
    """Seal local assets and import with Recs' explicit stereo/48 kHz output policy."""
    source = sfz.parse(path.read_text(encoding='utf-8-sig'))
    root = path.parent.resolve()
    assets = {}
    for reference in sfz.sample_paths(source):
        sample = root.joinpath(reference).resolve()
        if not sample.is_relative_to(root):
            raise ValueError(
                f'SFZ sample escapes the instrument directory: {reference}'
            )
        assets[reference] = read_audio_metadata(sample)
    return sfz.compile(
        source,
        id=path.stem,
        name=path.stem,
        assets=assets,
        output_timebase=Timebase(id='output', rate=Rate(numerator=output_rate)),
        output_channels=output_channels
        if output_channels is not None
        else ['left', 'right'],
    )
