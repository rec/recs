from functools import cached_property

import numpy as np

from recs.edit.automation import gain_values
from recs.edit.graph import EditGraph, FrameRange
from recs.edit.materialized import MaterializedAudio, materialize_source, merge_ranges
from recs.edit.record import ResolvedSource
from recs.edit.schema import EditSpec, NormalizeMode, OutputSpec


class Renderer:
    def __init__(
        self,
        edit: EditSpec,
        sources: dict[str, ResolvedSource],
        graph: EditGraph,
    ) -> None:
        self.edit = edit
        self.sources = {k: materialize_source(v) for k, v in sources.items()}
        self.graph = graph

    def render(self, output: OutputSpec) -> MaterializedAudio:
        return self.outputs[output.id]

    @cached_property
    def outputs(self) -> dict[str, MaterializedAudio]:
        nodes, ranges = self._nodes()
        result: dict[str, MaterializedAudio] = {}
        for output in self.edit.outputs:
            frame_range = self.graph.output_extents[output.id]
            samples = nodes[output.source][frame_range.start : frame_range.end]
            scale = output.gain
            if output.normalize != NormalizeMode.none:
                peak = float(np.max(np.abs(samples))) if samples.size else 0.0
                if peak > 0 and (
                    output.normalize == NormalizeMode.normalize or peak > 1
                ):
                    scale /= peak
            if scale != 1:
                samples = samples * np.float32(scale)
            observed = _intersect_ranges(ranges[output.source], frame_range)
            result[output.id] = MaterializedAudio(
                np.asarray(samples, dtype=np.float32),
                self.edit.sample_rate,
                frame_range.start,
                observed,
            )
        return result

    def _nodes(self) -> tuple[dict[str, np.ndarray], dict[str, list[FrameRange]]]:
        timeline_end = max(r.end for r in self.graph.output_extents.values())
        nodes = {
            t.id: np.zeros((timeline_end, t.channels), dtype=np.float32)
            for t in self.edit.tracks
        }
        ranges: dict[str, list[FrameRange]] = {t.id: [] for t in self.edit.tracks}
        automation = {a.target: a for a in self.edit.automation}
        for clip in self.edit.clips:
            clip_start = clip.timeline_start
            clip_end = clip_start + clip.source_end - clip.source_start
            overlap_start = max(0, clip_start)
            overlap_end = min(timeline_end, clip_end)
            if overlap_start >= overlap_end:
                continue
            source = self.sources[clip.source]
            source_start = clip.source_start + overlap_start - clip_start
            source_end = source_start + overlap_end - overlap_start
            source_samples = source.samples[source_start:source_end]
            gains = gain_values(
                automation.get(f'clip:{clip.id}:gain'),
                clip.gain,
                overlap_start,
                overlap_end - overlap_start,
            )
            nodes[clip.track][overlap_start:overlap_end] += (
                source_samples * gains[:, np.newaxis]
            )
            ranges[clip.track].extend(
                _map_ranges(
                    source.observed_ranges,
                    source_start,
                    source_end,
                    overlap_start,
                )
            )

        buses = {b.id: b for b in self.edit.buses}
        routes = {b.id: [] for b in self.edit.buses}
        for route in self.edit.routes:
            routes[route.destination].append(route)
        for bus_id in self.graph.bus_order:
            bus = buses[bus_id]
            block = np.zeros((timeline_end, bus.channels), dtype=np.float32)
            observed: list[FrameRange] = []
            for route in routes[bus_id]:
                gains = gain_values(
                    automation.get(f'route:{route.source}->{route.destination}:gain'),
                    route.gain,
                    0,
                    timeline_end,
                )
                block += nodes[route.source] * gains[:, np.newaxis]
                observed.extend(ranges[route.source])
            block *= gain_values(
                automation.get(f'bus:{bus.id}:gain'), bus.gain, 0, timeline_end
            )[:, np.newaxis]
            nodes[bus_id] = block
            ranges[bus_id] = merge_ranges(observed)
        return nodes, {k: merge_ranges(v) for k, v in ranges.items()}


def _map_ranges(
    values: list[FrameRange], source_start: int, source_end: int, timeline_start: int
) -> list[FrameRange]:
    return [
        FrameRange(
            start=timeline_start + max(source_start, r.start) - source_start,
            end=timeline_start + min(source_end, r.end) - source_start,
        )
        for r in values
        if max(source_start, r.start) < min(source_end, r.end)
    ]


def _intersect_ranges(
    values: list[FrameRange], frame_range: FrameRange
) -> list[FrameRange]:
    return [
        FrameRange(
            start=max(frame_range.start, r.start),
            end=min(frame_range.end, r.end),
        )
        for r in values
        if max(frame_range.start, r.start) < min(frame_range.end, r.end)
    ]
