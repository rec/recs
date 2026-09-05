from pydantic import BaseModel, ConfigDict

from recs.base.errors import RecsError
from recs.edit.record import ResolvedSource
from recs.edit.schema import EditSpec


class EditGraph(BaseModel, frozen=True):
    widths: dict[str, int]
    output_extents: dict[str, 'FrameRange']
    bus_order: list[str]

    model_config = ConfigDict(extra='forbid')


class FrameRange(BaseModel, frozen=True):
    start: int
    end: int

    model_config = ConfigDict(extra='forbid')


def validate_graph(edit: EditSpec, sources: dict[str, ResolvedSource]) -> EditGraph:
    _unique('source', [s.id for s in edit.sources])
    _unique('track', [t.id for t in edit.tracks])
    _unique('bus', [b.id for b in edit.buses])
    _unique('clip', [c.id for c in edit.clips])
    _unique('output', [o.id for o in edit.outputs])
    _unique('automation target', [a.target for a in edit.automation])

    track_widths = {t.id: t.channels for t in edit.tracks}
    bus_widths = {b.id: b.channels for b in edit.buses}
    overlap = set(track_widths) & set(bus_widths)
    if overlap:
        raise RecsError(f'Track and bus IDs collide: {sorted(overlap)}')
    widths = track_widths | bus_widths

    clip_extents: dict[str, int] = dict.fromkeys(track_widths, 0)
    for clip in edit.clips:
        source = sources.get(clip.source)
        if source is None:
            raise RecsError(f'Clip {clip.id}: unknown source {clip.source}')
        width = track_widths.get(clip.track)
        if width is None:
            raise RecsError(f'Clip {clip.id}: unknown track {clip.track}')
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

    destinations: dict[str, list[str]] = {b.id: [] for b in edit.buses}
    for route in edit.routes:
        if route.source not in widths:
            raise RecsError(f'Route has unknown source {route.source}')
        if route.destination not in bus_widths:
            raise RecsError(f'Route has unknown destination bus {route.destination}')
        if widths[route.source] != bus_widths[route.destination]:
            raise RecsError(
                f'Route {route.source}->{route.destination}: channel widths differ'
            )
        destinations[route.destination].append(route.source)
    bus_order = _bus_order(destinations, bus_widths)

    extents = dict(clip_extents)
    for bus in bus_order:
        extents[bus] = max((extents[s] for s in destinations[bus]), default=0)

    clip_ids = {c.id for c in edit.clips}
    route_ids = {(r.source, r.destination) for r in edit.routes}
    bus_ids = set(bus_widths)
    for automation in edit.automation:
        _validate_target(automation.target, clip_ids, route_ids, bus_ids)

    output_extents: dict[str, FrameRange] = {}
    for output in edit.outputs:
        if output.source not in widths:
            raise RecsError(f'Output {output.id}: unknown source {output.source}')
        start = output.start or 0
        end = output.end if output.end is not None else extents[output.source]
        if end <= start:
            raise RecsError(f'Output {output.id}: empty frame range {start}:{end}')
        output_extents[output.id] = FrameRange(start=start, end=end)
    return EditGraph(widths=widths, output_extents=output_extents, bus_order=bus_order)


def _unique(kind: str, values: list[str]) -> None:
    duplicates = sorted({v for v in values if values.count(v) > 1})
    if duplicates:
        raise RecsError(f'Duplicate {kind} IDs: {duplicates}')


def _bus_order(
    destinations: dict[str, list[str]], bus_widths: dict[str, int]
) -> list[str]:
    result: list[str] = []
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(bus: str) -> None:
        if bus in visiting:
            raise RecsError(f'Routing cycle includes bus {bus}')
        if bus in visited:
            return
        visiting.add(bus)
        for source in destinations[bus]:
            if source in bus_widths:
                visit(source)
        visiting.remove(bus)
        visited.add(bus)
        result.append(bus)

    for bus in destinations:
        visit(bus)
    return result


def _validate_target(
    target: str,
    clip_ids: set[str],
    route_ids: set[tuple[str, str]],
    bus_ids: set[str],
) -> None:
    parts = target.split(':')
    if len(parts) != 3 or parts[2] != 'gain':
        raise RecsError(f'Unsupported automation target {target!r}')
    kind, identity, _ = parts
    valid = False
    if kind == 'clip':
        valid = identity in clip_ids
    elif kind == 'bus':
        valid = identity in bus_ids
    elif kind == 'route' and '->' in identity:
        source, destination = identity.split('->', 1)
        valid = (source, destination) in route_ids
    if not valid:
        raise RecsError(f'Unknown automation target {target!r}')
