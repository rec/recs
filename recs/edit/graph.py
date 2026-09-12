from collections.abc import Mapping
from typing import Protocol

from pydantic import BaseModel, ConfigDict
from ufor.arrangement import ArrangementScore
from ufor.interface import MixBinding, OutputSelection

from recs.base.errors import RecsError


class AudioDescription(Protocol):
    @property
    def channels(self) -> int: ...

    @property
    def timeline_end(self) -> int: ...


class EditGraph(BaseModel, frozen=True):
    widths: dict[str, int]
    output_extents: dict[str, 'FrameRange']
    bus_order: list[str]

    model_config = ConfigDict(extra='forbid')


class FrameRange(BaseModel, frozen=True):
    start: int
    end: int

    model_config = ConfigDict(extra='forbid')


def validate_graph(
    edit: ArrangementScore, sources: Mapping[OutputSelection, AudioDescription]
) -> EditGraph:
    track_widths = {t.name: len(t.stream.channels) for t in edit.body.tracks}
    bus_widths = {b.name: len(b.stream.channels) for b in edit.body.buses}
    widths = track_widths | bus_widths

    clip_extents: dict[str, int] = dict.fromkeys(track_widths, 0)
    for clip in edit.body.clips:
        source = sources.get(clip.source)
        if source is None:
            raise RecsError(f'Clip {clip.name}: unknown source {clip.source}')
        width = track_widths[clip.track]
        if source.channels != width:
            raise RecsError(
                f'Clip {clip.name}: source width {source.channels} does not match '
                f'track width {width}'
            )
        if clip.source_end > source.timeline_end:
            raise RecsError(
                f'Clip {clip.name}: source range ends at {clip.source_end}, beyond '
                f'{clip.source} timeline end {source.timeline_end}'
            )
        clip_extents[clip.track] = max(
            clip_extents[clip.track],
            clip.timeline_start + clip.source_end - clip.source_start,
        )

    destinations: dict[str, list[str]] = {b.name: [] for b in edit.body.buses}
    for route in edit.body.routes:
        destinations[route.destination].append(route.source)
    bus_order = edit.body.bus_order

    extents = dict(clip_extents)
    for bus in bus_order:
        extents[bus] = max((extents[s] for s in destinations[bus]), default=0)

    output_extents: dict[str, FrameRange] = {}
    for output in edit.outputs:
        if isinstance(output.binding, OutputSelection):
            source = sources[output.binding]
            output_extents[output.name] = FrameRange(
                start=getattr(source, 'start_frame', 0), end=source.timeline_end
            )
            continue
        assert isinstance(output.binding, MixBinding)
        start = output.binding.start or 0
        end = (
            output.binding.end
            if output.binding.end is not None
            else extents[str(output.binding.track or output.binding.bus)]
        )
        if end <= start:
            raise RecsError(f'Output {output.name}: empty frame range {start}:{end}')
        output_extents[output.name] = FrameRange(start=start, end=end)
    return EditGraph(widths=widths, output_extents=output_extents, bus_order=bus_order)
