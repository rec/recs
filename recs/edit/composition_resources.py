"""Plan composition stages without materializing their audio."""

import tempfile
from pathlib import Path

from ufor.arrangement import ArrangementScore
from ufor.interface import ScoreVersion
from ufor.recording import AudioStream, Gap, Recording, RecordingScore, stream_outputs
from ufor.streams import AudioType
from ufor.time import Rate, Timebase

from ..base.errors import RecsError
from . import commands
from .composition import CompositionEdit, resolve_composition
from .inputs import SourceSpec
from .resources import ResourcePlan, plan_edit
from .schema import CommandKind
from .workspace import SCRATCH_DIRECTORY


def plan_composition(
    value: CompositionEdit, path: Path, record: Path, destination: Path
) -> tuple[ResourcePlan, list[str]]:
    tracks = commands.input_tracks([record])
    resolved = resolve_composition(value, path.parent)
    plans: list[ResourcePlan] = []
    lines: list[str] = []
    memory: dict[str, commands.InputTrack] = {}
    unknown: list[str] = []
    analysis_source_bytes = 0
    for index, step in enumerate(resolved, 1):
        lines.extend(
            [
                f'{index}: {step.step.command}',
                '   Selectors: '
                + (', '.join(step.step.channel) or 'all compatible tracks'),
            ]
        )
        if index < len(resolved) and (
            step.step.format is not None or step.step.subtype is not None
        ):
            raise RecsError(
                'Composition intermediate encoding is unsupported; '
                'only the final edit may set format or subtype'
            )
        if commands.command_operation(step.recipe) == CommandKind.autocalibrate:
            selected = commands.select_tracks(tracks, step.step.channel)
            analysis_source_bytes = sum(
                t.frame_count * t.channels * 4 for t in selected
            )
            unknown.append(
                f'Stage {index} calibration and subsequent stages '
                'require audio analysis'
            )
            break
        definitions: dict[Path, RecordingScore] = {}
        if value.stages:
            stage = value.stages[index - 1]
            if (
                stage.command != step.step.command
                or stage.operation != commands.command_operation(step.recipe)
            ):
                raise RecsError(f'Resolved stage {index} does not match its edit')
            edit = ArrangementScore.model_validate(stage.edit)
        else:
            edit = commands.complete_or_generate_tracks(
                step.recipe, tracks, step.step, definitions
            )
        origin = (
            path.parent
            if value.stages
            else step.command_path.parent
            if step.recipe.get('kind') == 'arrangement'
            else Path.cwd()
        )
        for part in edit.body.parts:
            if not isinstance(part.score, ScoreVersion) or part.score.path is None:
                continue
            reference = Path(part.score.path)
            if reference.parts[0] != 'prepared':
                continue
            key = ':'.join(reference.parts[1:-1])
            if key not in memory:
                raise RecsError(f'Unknown prepared source: {key}')
            track = memory[key]
            channels = [
                int(i) for i in reference.stem.removeprefix('channels-').split('-')
            ]
            if any(c >= track.channels for c in channels):
                raise RecsError(f'Prepared channel exceeds width: {reference}')
            stream = AudioStream(
                name='audio',
                source_id=key,
                stream=AudioType(
                    timebase='audio', channels=[f'channel-{c}' for c in channels]
                ),
                end=track.frame_count,
                gaps=[Gap(start=0, end=track.frame_count, reason='unknown')]
                if track.frame_count
                else [],
            )
            # A metadata-only, in-memory description, never a published recording.
            definitions[(origin / reference).resolve()] = RecordingScore(
                name=part.name,
                title='Prepared audio metadata',
                assets=[],
                timebases=[
                    Timebase(name='audio', rate=Rate(numerator=track.sample_rate))
                ],
                outputs=stream_outputs([stream]),
                body=Recording(state='sealed', streams=[stream]),
            )
        plan = plan_edit(
            edit, origin, destination, definitions, final=index == len(resolved)
        )
        plans.append(plan)
        lines.append(
            f'   Temporary audio storage: {plan.intermediate_storage_bytes} bytes'
        )
        tracks = []
        for output in edit.outputs:
            if not isinstance(output.stream, AudioType):
                raise RecsError('Composition planning requires audio outputs')
            key = f'stage-{index:03d}:{output.name}'
            width = len(output.stream.channels)
            # Explicit output origins remain part of the source timeline.
            start = getattr(output.binding, 'start', None) or 0
            track = commands.InputTrack(
                label=f'edit:{output.name}',
                selectors=[f'edit:{output.name}'],
                source=SourceSpec(
                    name='source', memory=key, channels=list(range(width))
                ),
                channels=width,
                sample_rate=edit.timebases[0].rate.numerator,
                frame_count=start + plan.output_frames[output.name],
            )
            tracks.append(track)
            memory[key] = track
    last = plans[-1] if plans else None
    return ResourcePlan(
        scratch_directory=SCRATCH_DIRECTORY.get() or Path(tempfile.gettempdir()),
        destination=destination,
        source_storage_bytes=analysis_source_bytes
        + sum(p.source_storage_bytes for p in plans),
        intermediate_storage_bytes=sum(p.intermediate_storage_bytes for p in plans),
        working_ram_bytes=None
        if unknown
        else max((p.working_ram_bytes or 0 for p in plans), default=0),
        destination_bytes=last.destination_bytes if last and not unknown else None,
        known_destination_bytes=last.known_destination_bytes
        if last and not unknown
        else 0,
        output_frames=last.output_frames if last and not unknown else {},
        unknown=unknown + (last.unknown if last else []),
    ), lines
