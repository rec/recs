from collections.abc import Mapping
from functools import cached_property

import numpy as np
from ufor.arrangement import ArrangementScore, ControlClip
from ufor.automation import ArrangementGainTarget, AutomationScore
from ufor.interface import MixBinding, NormalizeMode, Output, OutputSelection

from recs.base.errors import RecsError
from recs.edit import materialized
from recs.edit.automation import gain_values
from recs.edit.graph import EditGraph, FrameRange
from recs.edit.materialized import MaterializedAudio, SourceMaterializer
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
        source_width = max(
            (s.storage.channels for s in self.sources.values()), default=0
        )
        self.peak_memory_bytes = max(
            max(
                (s.storage.peak_buffer_bytes for s in self.sources.values()), default=0
            ),
            materialized.estimate_audio_buffers(graph.widths, source_width),
        )

    def render(self, output: Output) -> MaterializedAudio:
        return self.outputs[output.name]

    @cached_property
    def outputs(self) -> dict[str, MaterializedAudio]:
        ranges = self._ranges()
        automation = self._automation()
        result: dict[str, MaterializedAudio] = {}
        mixes = []
        peaks: dict[str, float] = {}
        for output in self.edit.outputs:
            if isinstance(output.binding, OutputSelection):
                result[output.name] = self.sources[output.binding]
                continue
            binding = output.binding
            assert isinstance(binding, MixBinding)
            mixes.append(output)
            extent = self.graph.output_extents[output.name]
            node = str(binding.track or binding.bus)
            result[output.name] = MaterializedAudio(
                materialized.AudioStorage(
                    extent.end - extent.start, self.graph.widths[node]
                ),
                self.edit.timebases[0].rate.numerator,
                extent.start,
                _intersect_ranges(ranges[node], extent),
            )
            peaks[output.name] = 0.0
        if not mixes:
            return result
        start = min(self.graph.output_extents[o.name].start for o in mixes)
        end = max(self.graph.output_extents[o.name].end for o in mixes)
        for position in range(start, end, materialized.BLOCK_FRAMES):
            frames = min(materialized.BLOCK_FRAMES, end - position)
            parts = self._nodes(position, frames, automation)
            for output in mixes:
                binding = output.binding
                assert isinstance(binding, MixBinding)
                audio = result[output.name]
                left = max(position, audio.start_frame)
                right = min(position + frames, audio.end_frame)
                if left >= right:
                    continue
                samples = parts[str(binding.track or binding.bus)][
                    left - position : right - position
                ]
                audio.storage.write(left - audio.start_frame, samples)
                if binding.normalize != NormalizeMode.none:
                    peaks[output.name] = max(
                        peaks[output.name], float(np.max(np.abs(samples)))
                    )
            # Do not retain the previous node buffers during the next allocation.
            samples = None
            del parts
        for output in mixes:
            binding = output.binding
            assert isinstance(binding, MixBinding)
            scale = binding.gain
            peak = peaks[output.name]
            if peak > 0 and (binding.normalize == NormalizeMode.normalize or peak > 1):
                scale /= peak
            if scale != 1:
                audio = result[output.name]
                position = 0
                for block in audio.blocks():
                    audio.storage.write(position, block * np.float32(scale))
                    position += len(block)
        return result

    def _nodes(
        self,
        start: int,
        frames: int,
        automation: dict[ArrangementGainTarget, tuple[ControlClip, AutomationScore]],
    ) -> dict[str, np.ndarray]:
        end = start + frames
        parts = {
            t.name: materialized.allocate_audio(
                frames, len(t.stream.channels), f'track {t.name}'
            )
            for t in self.edit.body.tracks
        }
        for clip in self.edit.body.clips:
            left = max(start, clip.timeline_start)
            right = min(end, clip.timeline_start + clip.source_end - clip.source_start)
            if left >= right:
                continue
            source_start = clip.source_start + left - clip.timeline_start
            samples = _source_samples(
                self.sources[clip.source], source_start, source_start + right - left
            )
            gains = gain_values(
                automation.get(ArrangementGainTarget(kind='clip', name=clip.name)),
                clip.gain,
                left,
                right - left,
            )
            parts[clip.track][left - start : right - start] += (
                samples * gains[:, np.newaxis]
            )
        buses = {b.name: b for b in self.edit.body.buses}
        for bus_id in self.graph.bus_order:
            bus = buses[bus_id]
            block = materialized.allocate_audio(
                frames, len(bus.stream.channels), f'bus {bus.name}'
            )
            for route in self.edit.body.routes:
                if route.destination != bus_id:
                    continue
                gains = gain_values(
                    automation.get(
                        ArrangementGainTarget(
                            kind='route',
                            name=route.source,
                            destination=route.destination,
                        )
                    ),
                    route.gain,
                    start,
                    frames,
                )
                block += parts[route.source] * gains[:, np.newaxis]
            block *= gain_values(
                automation.get(ArrangementGainTarget(kind='bus', name=bus.name)),
                bus.gain,
                start,
                frames,
            )[:, np.newaxis]
            parts[bus_id] = block
        return parts

    def _ranges(self) -> dict[str, list[FrameRange]]:
        ranges: dict[str, list[FrameRange]] = {
            t.name: [] for t in self.edit.body.tracks
        }
        for clip in self.edit.body.clips:
            ranges[clip.track].extend(
                _map_ranges(
                    self.sources[clip.source].observed_ranges,
                    clip.source_start,
                    clip.source_end,
                    clip.timeline_start,
                )
            )
        for bus in self.graph.bus_order:
            ranges[bus] = materialized.merge_ranges(
                [
                    r
                    for route in self.edit.body.routes
                    if route.destination == bus
                    for r in ranges[route.source]
                ]
            )
        return {k: materialized.merge_ranges(v) for k, v in ranges.items()}

    def _automation(
        self,
    ) -> dict[ArrangementGainTarget, tuple[ControlClip, AutomationScore]]:
        parts = {p.name: p for p in self.edit.body.parts}
        result = {}
        for clip in self.edit.body.control_clips:
            part = parts[clip.source.name]
            if not isinstance(part.score, AutomationScore):
                raise RecsError(f'Control clip {clip.name}: source is not automation')
            score = part.score
            if score.timebases[0].rate != self.edit.timebases[0].rate:
                raise RecsError(
                    f'Control clip {clip.name}: automation rate must match audio rate'
                )
            if not isinstance(score.body.target, ArrangementGainTarget):
                raise RecsError(
                    f'Control clip {clip.name}: automation target is not an '
                    'arrangement gain'
                )
            result[score.body.target] = clip, score
        return result


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
            start=max(frame_range.start, r.start), end=min(frame_range.end, r.end)
        )
        for r in values
        if max(frame_range.start, r.start) < min(frame_range.end, r.end)
    ]


def _source_samples(source: MaterializedAudio, start: int, end: int) -> np.ndarray:
    result = materialized.allocate_audio(
        end - start, source.channels, 'clip source interval'
    )
    for observed in source.observed_ranges:
        left = max(start, observed.start)
        right = min(end, observed.end)
        if left < right:
            result[left - start : right - start] = source.read(left, right - left)
    return result
