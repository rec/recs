"""Metadata-only estimates using the same score loader and graph validator."""

import tempfile
from pathlib import Path

import soundfile
from pydantic import BaseModel, Field
from ufor.arrangement import ArrangementScore
from ufor.interface import MixBinding, OutputSelection, StreamBinding
from ufor.recording import AudioStream, RecordingScore
from ufor.streams import AudioType

from ..base.errors import RecsError
from ..recording.read import read_recording_chain
from . import commands
from .graph import validate_graph
from .materialized import BLOCK_FRAMES, estimate_audio_buffers
from .nested import load_composition
from .output import validate_outputs
from .workspace import SCRATCH_DIRECTORY, check_space


class AudioMetadata(BaseModel, frozen=True):
    channels: int
    timeline_end: int
    start_frame: int = 0


class ResourcePlan(BaseModel, frozen=True):
    scratch_directory: Path
    destination: Path
    source_storage_bytes: int = 0
    intermediate_storage_bytes: int = 0
    working_ram_bytes: int | None = 0
    destination_bytes: int | None = 0
    known_destination_bytes: int = 0
    output_frames: dict[str, int] = Field(default_factory=dict)
    unknown: list[str] = Field(default_factory=list)

    def check(self) -> None:
        check_space(
            self.source_storage_bytes + self.intermediate_storage_bytes,
            self.destination,
            self.known_destination_bytes,
            self.scratch_directory,
        )

    def summary(self) -> str:
        ram = (
            self.working_ram_bytes if self.working_ram_bytes is not None else 'unknown'
        )
        encoded = (
            self.destination_bytes if self.destination_bytes is not None else 'unknown'
        )
        lines = [
            f'Scratch directory: {self.scratch_directory}',
            f'Source float32 storage: {self.source_storage_bytes} bytes',
            f'Intermediate float32 storage: {self.intermediate_storage_bytes} bytes',
            f'Estimated peak audio buffers: {ram} bytes',
            f'Destination audio estimate: {encoded} bytes',
            f'Known destination audio subtotal: {self.known_destination_bytes} bytes',
            *[f'Output {k}: {v} frames' for k, v in self.output_frames.items()],
            *[f'Unknown: {u}' for u in self.unknown],
            'Estimates use full logical storage without sparse-file savings; all '
            'intermediates are counted as live together. RAM covers audio buffers, '
            'not Python or decoder overhead. Compressed sizes are unknown. '
            'WAV estimates include 4096 bytes per file, not session metadata. '
            'Free-space checks do not reserve capacity. '
            'Media integrity is checked at render time.',
            'When any stage is unknown, reported storage totals cover only known work.',
            'Composition totals may count shared sources and prepared views '
            'more than once.',
            'Recording metadata supplies frame/rate/channel estimates; rendering '
            'still inspects audio headers and verifies referenced assets.',
        ]
        return '\n'.join(lines) + '\n'


def plan_calibration(
    record: Path, selectors: list[str], destination: Path
) -> ResourcePlan:
    tracks = commands.select_tracks(commands.input_tracks([record]), selectors)
    if destination.exists():
        raise RecsError(f'Output session directory already exists: {destination}')
    return ResourcePlan(
        scratch_directory=SCRATCH_DIRECTORY.get() or Path(tempfile.gettempdir()),
        destination=destination,
        source_storage_bytes=sum(t.frame_count * t.channels * 4 for t in tracks),
        working_ram_bytes=None,
        destination_bytes=None,
        unknown=[
            'Calibration intervals, output frames, analysis RAM, and encoded size '
            'require audio analysis'
        ],
    )


def plan_edit(
    edit: ArrangementScore,
    directory: Path,
    destination: Path,
    supplied: dict[Path, RecordingScore] | None = None,
    *,
    final: bool = True,
) -> ResourcePlan:
    composition = load_composition(edit, directory, supplied=supplied)
    sources: dict[str, int] = {}
    outputs: dict[str, dict[str, AudioMetadata]] = {}
    intermediate = memory = 0

    def port(path: str, name: str) -> AudioMetadata:
        nonlocal intermediate, memory
        part = composition.parts[path]
        score = composition.scores[part.score].score
        output = composition.output(path, name)
        if not isinstance(output.stream, AudioType):
            raise RecsError('Audio planning requires audio ports')
        if isinstance(output.binding, OutputSelection):
            return port(part.children[output.binding.name], output.binding.output)
        if isinstance(score, RecordingScore) and isinstance(
            output.binding, StreamBinding
        ):
            stream = next(
                s for s in score.body.streams if s.name == output.binding.stream
            )
            if not isinstance(stream, AudioStream):
                raise RecsError('Audio planning requires audio recording ports')
            records = [(Path(part.score), score)]
            if score.body.continued_at or score.body.continued_from:
                records = read_recording_chain(Path(part.score))
            selected = [
                (d, s)
                for _, d in records
                for s in d.body.streams
                if isinstance(s, AudioStream)
                and s.name == stream.name
                and (s.source_name or s.source_id)
                == (stream.source_name or stream.source_id)
                and (s.track_name or s.name) == (stream.track_name or stream.name)
            ]
            if any(
                d.body.state != 'sealed' or s.unmapped_fragments for d, s in selected
            ):
                raise RecsError(
                    'Planning requires sealed audio with resolved placement'
                )
            clocks = [
                t
                for d, s in selected
                for t in d.timebases
                if t.name == s.stream.timebase
            ]
            if (
                len({(t.name, t.rate.numerator, t.rate.denominator) for t in clocks})
                != 1
                or any(t.rate.denominator != 1 for t in clocks)
                or len({len(s.stream.channels) for _, s in selected}) != 1
            ):
                raise RecsError(
                    'Independent or incompatible source clocks require alignment'
                )
            width = len(output.stream.channels)
            end = max(s.end for _, s in selected)
            sources[f'{part.score}:{stream.name}:{output.binding.channels}'] = (
                end * width * 4
            )
            memory = max(
                memory, BLOCK_FRAMES * (len(stream.stream.channels) + width) * 4
            )
            return AudioMetadata(channels=width, timeline_end=end)
        if not isinstance(score, ArrangementScore):
            raise RecsError(f'Audio planning of {score.kind} is unsupported')
        if path not in outputs:
            outputs[path] = arrangement(path, score)
        return outputs[path][name]

    def arrangement(path: str, score: ArrangementScore) -> dict[str, AudioMetadata]:
        nonlocal intermediate, memory
        if score.body.media_types != ['audio']:
            raise RecsError('Offline planning supports only media_types = ["audio"]')
        if score.inputs or score.body.connections:
            raise RecsError('Offline planning requires unconnected audio arrangements')
        addresses = {c.source for c in score.body.clips} | {
            o.binding for o in score.outputs if isinstance(o.binding, OutputSelection)
        }
        inputs = {
            a: port(composition.parts[path].children[a.name], a.output)
            for a in addresses
        }
        graph = validate_graph(score, inputs)
        if path == 'root' and final:
            validate_outputs(score, graph, destination)
        result = {}
        source_width = max((s.channels for s in inputs.values()), default=0)
        memory = max(
            memory,
            estimate_audio_buffers(graph.widths, source_width),
        )
        for output in score.outputs:
            if not isinstance(output.stream, AudioType):
                raise RecsError('Audio planning requires audio ports')
            extent = graph.output_extents[output.name]
            result[output.name] = AudioMetadata(
                channels=len(output.stream.channels),
                start_frame=extent.start,
                timeline_end=extent.end,
            )
            if isinstance(output.binding, MixBinding):
                intermediate += (
                    (extent.end - extent.start) * len(output.stream.channels) * 4
                )
        return result

    result = arrangement('root', edit)
    encoded = 0
    unknown = []
    for target in edit.destinations:
        subtype = target.subtype or soundfile.default_subtype(target.format)
        size = {
            'PCM_16': 2,
            'PCM_24': 3,
            'PCM_32': 4,
            'FLOAT': 4,
            'DOUBLE': 8,
            'PCM_U8': 1,
            'PCM_S8': 1,
        }.get(str(subtype).upper())
        audio = result[target.output]
        if target.format != 'wav' or size is None:
            unknown.append(
                f'Encoded size of {target.output} ({target.format}/{subtype})'
            )
        else:
            encoded += (
                audio.timeline_end - audio.start_frame
            ) * audio.channels * size + 4096
    return ResourcePlan(
        scratch_directory=SCRATCH_DIRECTORY.get() or Path(tempfile.gettempdir()),
        destination=destination,
        source_storage_bytes=sum(sources.values()),
        intermediate_storage_bytes=intermediate,
        working_ram_bytes=memory,
        destination_bytes=None if unknown else encoded,
        known_destination_bytes=encoded,
        output_frames={k: v.timeline_end - v.start_frame for k, v in result.items()},
        unknown=unknown,
    )
