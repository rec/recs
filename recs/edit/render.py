from collections import OrderedDict
from pathlib import Path

import numpy as np
import soundfile

from recs.base.errors import RecsError
from recs.edit.automation import gain_values
from recs.edit.graph import EditGraph
from recs.edit.output import open_output
from recs.edit.record import ResolvedSource
from recs.edit.schema import EditSpec, NormalizeMode, OutputSpec

BLOCK_FRAMES = 4096


class Renderer:
    def __init__(
        self,
        edit: EditSpec,
        sources: dict[str, ResolvedSource],
        graph: EditGraph,
    ) -> None:
        self.edit = edit
        self.sources = sources
        self.graph = graph
        self.automation = {a.target: a for a in edit.automation}
        self.readers: OrderedDict[Path, soundfile.SoundFile] = OrderedDict()

    def render_output(self, output: OutputSpec, path: Path) -> int:
        frame_range = self.graph.output_extents[output.id]
        try:
            scale = output.gain
            if output.normalize != NormalizeMode.none:
                peak = self._peak(output.source, frame_range.start, frame_range.end)
                if peak > 0 and (
                    output.normalize == NormalizeMode.normalize or peak > 1
                ):
                    scale /= peak
            fp = open_output(
                output,
                path,
                self.graph.widths[output.source],
                self.edit.sample_rate,
            )
            try:
                for start in range(frame_range.start, frame_range.end, BLOCK_FRAMES):
                    end = min(start + BLOCK_FRAMES, frame_range.end)
                    fp.write(self._nodes(start, end)[output.source] * scale)
            finally:
                fp.close()
        finally:
            self._close_readers()
        return frame_range.end - frame_range.start

    def _peak(self, source: str, start: int, end: int) -> float:
        peak = 0.0
        for position in range(start, end, BLOCK_FRAMES):
            block = self._nodes(position, min(position + BLOCK_FRAMES, end))[source]
            if block.size:
                peak = max(peak, float(np.max(np.abs(block))))
        return peak

    def _nodes(self, start: int, end: int) -> dict[str, np.ndarray]:
        frames = end - start
        nodes = {
            track.id: np.zeros((frames, track.channels), dtype=np.float32)
            for track in self.edit.tracks
        }
        for clip in self.edit.clips:
            clip_start = clip.timeline_start
            clip_end = clip_start + clip.source_end - clip.source_start
            overlap_start = max(start, clip_start)
            overlap_end = min(end, clip_end)
            if overlap_start >= overlap_end:
                continue
            source_start = clip.source_start + overlap_start - clip_start
            block = self._read_source(
                self.sources[clip.source],
                source_start,
                source_start + overlap_end - overlap_start,
            )
            automation = self.automation.get(f'clip:{clip.id}:gain')
            gains = gain_values(
                automation, clip.gain, overlap_start, overlap_end - overlap_start
            )
            nodes[clip.track][overlap_start - start : overlap_end - start] += (
                block * gains[:, np.newaxis]
            )

        buses = {b.id: b for b in self.edit.buses}
        routes = {b.id: [] for b in self.edit.buses}
        for route in self.edit.routes:
            routes[route.destination].append(route)
        for bus_id in self.graph.bus_order:
            bus = buses[bus_id]
            block = np.zeros((frames, bus.channels), dtype=np.float32)
            for route in routes[bus_id]:
                automation = self.automation.get(
                    f'route:{route.source}->{route.destination}:gain'
                )
                gains = gain_values(automation, route.gain, start, frames)
                block += nodes[route.source] * gains[:, np.newaxis]
            automation = self.automation.get(f'bus:{bus.id}:gain')
            block *= gain_values(automation, bus.gain, start, frames)[:, np.newaxis]
            nodes[bus_id] = block
        return nodes

    def _read_source(self, source: ResolvedSource, start: int, end: int) -> np.ndarray:
        result = np.zeros((end - start, source.channels), dtype=np.float32)
        for fragment in source.fragments:
            overlap_start = max(start, fragment.start)
            overlap_end = min(end, fragment.end)
            if overlap_start >= overlap_end:
                continue
            try:
                fp = self._reader(fragment.path)
                fp.seek(overlap_start - fragment.start)
                data = fp.read(
                    overlap_end - overlap_start,
                    dtype='float32',
                    always_2d=True,
                )
            except soundfile.SoundFileError as e:
                raise RecsError(f'Cannot read source audio {fragment.path}: {e}') from e
            first = fragment.channel_offset
            result[overlap_start - start : overlap_end - start] = data[
                :, first : first + source.channels
            ]
        return result

    def _reader(self, path: Path) -> soundfile.SoundFile:
        if fp := self.readers.pop(path, None):
            self.readers[path] = fp
            return fp
        fp = soundfile.SoundFile(path)
        self.readers[path] = fp
        if len(self.readers) > 8:
            _, oldest = self.readers.popitem(last=False)
            oldest.close()
        return fp

    def _close_readers(self) -> None:
        for fp in self.readers.values():
            fp.close()
        self.readers.clear()
