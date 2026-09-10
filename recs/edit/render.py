from collections.abc import Mapping
from functools import cached_property

import numpy as np
from ufor.arrangement import ArrangementScore
from ufor.interface import MixBinding, NormalizeMode, Output, OutputSelection
from ufor.references import ParameterTarget

from recs.base.errors import RecsError
from recs.edit.automation import gain_values
from recs.edit.graph import EditGraph, FrameRange
from recs.edit.materialized import (
    MaterializedAudio,
    SourceMaterializer,
    allocate_audio,
    merge_ranges,
)
from recs.edit.record import ResolvedSource


class Renderer:
    def __init__(
        self,
        edit: ArrangementScore,
        sources: Mapping[OutputSelection, ResolvedSource | MaterializedAudio],
        graph: EditGraph,
        materializer: SourceMaterializer | None = None,
    ) -> None:
        self.edit = edit
        materializer = materializer or SourceMaterializer()
        self.sources = {
            k: v if isinstance(v, MaterializedAudio) else materializer.materialize(v)
            for k, v in sources.items()
        }
        self.graph = graph
        self.peak_memory_bytes = self._estimated_peak_memory_bytes()

    def render(self, output: Output) -> MaterializedAudio:
        return self.outputs[output.name]

    @cached_property
    def outputs(self) -> dict[str, MaterializedAudio]:
        try:
            return self._outputs()
        except MemoryError as e:
            raise RecsError(
                'Cannot allocate materialized edit audio; '
                f'at least {self.peak_memory_bytes} bytes are already live'
            ) from e

    def _outputs(self) -> dict[str, MaterializedAudio]:
        parts, ranges = self._nodes()
        result: dict[str, MaterializedAudio] = {}
        for output in self.edit.outputs:
            if isinstance(output.binding, OutputSelection):
                result[output.name] = self.sources[output.binding]
                continue
            assert isinstance(output.binding, MixBinding)
            frame_range = self.graph.output_extents[output.name]
            samples = parts[str(output.binding.track or output.binding.bus)][
                frame_range.start : frame_range.end
            ]
            scale = output.binding.gain
            if output.binding.normalize != NormalizeMode.none:
                peak = float(np.max(np.abs(samples))) if samples.size else 0.0
                if peak > 0 and (
                    output.binding.normalize == NormalizeMode.normalize or peak > 1
                ):
                    scale /= peak
            if scale != 1:
                samples = samples * np.float32(scale)
            samples.flags.writeable = False
            observed = _intersect_ranges(
                ranges[str(output.binding.track or output.binding.bus)], frame_range
            )
            result[output.name] = MaterializedAudio(
                np.asarray(samples, dtype=np.float32),
                self.edit.timebases[0].rate.numerator,
                frame_range.start,
                observed,
            )
        self.peak_memory_bytes = max(
            self.peak_memory_bytes,
            _storage_bytes(
                [s.samples for s in self.sources.values()]
                + list(parts.values())
                + [a.samples for a in result.values()]
            ),
        )
        return result

    def _nodes(self) -> tuple[dict[str, np.ndarray], dict[str, list[FrameRange]]]:
        timeline_end = max(r.end for r in self.graph.output_extents.values())
        parts = {
            t.name: allocate_audio(
                timeline_end, len(t.stream.channels), f'track {t.name}'
            )
            for t in self.edit.body.tracks
        }
        ranges: dict[str, list[FrameRange]] = {
            t.name: [] for t in self.edit.body.tracks
        }
        automation = {a.target: a for a in self.edit.body.automation}
        for clip in self.edit.body.clips:
            clip_start = clip.timeline_start
            clip_end = clip_start + clip.source_end - clip.source_start
            overlap_start = max(0, clip_start)
            overlap_end = min(timeline_end, clip_end)
            if overlap_start >= overlap_end:
                continue
            source = self.sources[clip.source]
            source_start = clip.source_start + overlap_start - clip_start
            source_end = source_start + overlap_end - overlap_start
            source_samples = _source_samples(source, source_start, source_end)
            gains = gain_values(
                automation.get(ParameterTarget(kind='clip', name=clip.name)),
                clip.gain,
                overlap_start,
                overlap_end - overlap_start,
            )
            parts[clip.track][overlap_start:overlap_end] += (
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

        buses = {b.name: b for b in self.edit.body.buses}
        routes = {b.name: [] for b in self.edit.body.buses}
        for route in self.edit.body.routes:
            routes[route.destination].append(route)
        for bus_id in self.graph.bus_order:
            bus = buses[bus_id]
            block = allocate_audio(
                timeline_end, len(bus.stream.channels), f'bus {bus.name}'
            )
            observed: list[FrameRange] = []
            for route in routes[bus_id]:
                gains = gain_values(
                    automation.get(
                        ParameterTarget(
                            kind='route',
                            name=route.source,
                            destination=route.destination,
                        )
                    ),
                    route.gain,
                    0,
                    timeline_end,
                )
                block += parts[route.source] * gains[:, np.newaxis]
                observed.extend(ranges[route.source])
            block *= gain_values(
                automation.get(ParameterTarget(kind='bus', name=bus.name)),
                bus.gain,
                0,
                timeline_end,
            )[:, np.newaxis]
            parts[bus_id] = block
            ranges[bus_id] = merge_ranges(observed)
        return parts, {k: merge_ranges(v) for k, v in ranges.items()}

    def _estimated_peak_memory_bytes(self) -> int:
        timeline_end = max(r.end for r in self.graph.output_extents.values())
        itemsize = np.dtype(np.float32).itemsize
        sources = _storage_bytes([s.samples for s in self.sources.values()])
        parts = (
            timeline_end
            * itemsize
            * (
                sum(len(t.stream.channels) for t in self.edit.body.tracks)
                + sum(len(b.stream.channels) for b in self.edit.body.buses)
            )
        )
        clip_temporary = max(
            (
                (c.source_end - c.source_start)
                * (2 * self.sources[c.source].channels + 1)
                * itemsize
                for c in self.edit.body.clips
            ),
            default=0,
        )
        route_temporary = max(
            (
                timeline_end * (self.graph.widths[r.source] + 1) * itemsize
                for r in self.edit.body.routes
            ),
            default=0,
        )
        persistent_outputs = 0
        peak = sources + parts + max(clip_temporary, route_temporary)
        for output in self.edit.outputs:
            if isinstance(output.binding, OutputSelection):
                continue
            assert isinstance(output.binding, MixBinding)
            frame_range = self.graph.output_extents[output.name]
            size = (
                (frame_range.end - frame_range.start)
                * self.graph.widths[str(output.binding.track or output.binding.bus)]
                * itemsize
            )
            transient = size if output.binding.normalize != NormalizeMode.none else 0
            peak = max(peak, sources + parts + persistent_outputs + transient)
            if (
                output.binding.gain != 1
                or output.binding.normalize != NormalizeMode.none
            ):
                persistent_outputs += size
            peak = max(peak, sources + parts + persistent_outputs)
        return peak


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


def _source_samples(source: MaterializedAudio, start: int, end: int) -> np.ndarray:
    result = allocate_audio(end - start, source.channels, 'clip source interval')
    for observed in source.observed_ranges:
        overlap_start = max(start, observed.start)
        overlap_end = min(end, observed.end)
        if overlap_start < overlap_end:
            result[overlap_start - start : overlap_end - start] = source.samples[
                overlap_start - source.start_frame : overlap_end - source.start_frame
            ]
    return result


def _storage_bytes(values: list[np.ndarray]) -> int:
    arrays: dict[int, np.ndarray] = {}
    for value in values:
        while isinstance(value.base, np.ndarray):
            value = value.base
        arrays[id(value)] = value
    return sum(a.nbytes for a in arrays.values())
