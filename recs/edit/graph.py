from collections.abc import Mapping
from typing import Protocol

from pydantic import BaseModel, ConfigDict
from ufor.arrangement import ArrangementDocument
from ufor.interface import Address, Direction, MixBinding

from recs.base.errors import RecsError


class AudioDescription(Protocol):
    channels: int
    timeline_end: int


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
    edit: ArrangementDocument, sources: Mapping[Address, AudioDescription]
) -> EditGraph:
    track_widths = {t.id: len(t.stream.channels) for t in edit.body.tracks}
    bus_widths = {b.id: len(b.stream.channels) for b in edit.body.buses}
    widths = track_widths | bus_widths

    clip_extents: dict[str, int] = dict.fromkeys(track_widths, 0)
    for clip in edit.body.clips:
        source = sources.get(clip.source)
        if source is None:
            raise RecsError(f'Clip {clip.id}: unknown source {clip.source}')
        width = track_widths[clip.track]
        if source.channels != width:
            raise RecsError(
                f'Clip {clip.id}: source width {source.channels} does not match '
                f'track width {width}'
            )
        if clip.source_end > source.timeline_end:
            raise RecsError(
                f'Clip {clip.id}: source range ends at {clip.source_end}, beyond '
                f'{clip.source} timeline end {source.timeline_end}'
            )
        clip_extents[clip.track] = max(
            clip_extents[clip.track],
            clip.timeline_start + clip.source_end - clip.source_start,
        )

    destinations: dict[str, list[str]] = {b.id: [] for b in edit.body.buses}
    for route in edit.body.routes:
        destinations[route.destination].append(route.source)
    bus_order = edit.body.bus_order

    extents = dict(clip_extents)
    for bus in bus_order:
        extents[bus] = max((extents[s] for s in destinations[bus]), default=0)

    output_extents: dict[str, FrameRange] = {}
    for output in edit.ports:
        if output.direction != Direction.output:
            continue
        if isinstance(output.binding, Address):
            source = sources[output.binding]
            output_extents[output.id] = FrameRange(
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
            raise RecsError(f'Output {output.id}: empty frame range {start}:{end}')
        output_extents[output.id] = FrameRange(start=start, end=end)
    return EditGraph(widths=widths, output_extents=output_extents, bus_order=bus_order)
