from collections.abc import Mapping
from pathlib import Path
from typing import Literal

import numpy as np
import tomlkit
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from typing_extensions import Self

from recs.base.errors import RecsError
from recs.edit import autocalibrate, commands, session
from recs.edit.graph import EditGraph, validate_graph
from recs.edit.materialized import (
    MaterializedAudio,
    MaterializedSession,
    MaterializedTrack,
    SourceMaterializer,
    select_channels,
)
from recs.edit.options import EditOptions
from recs.edit.output import validate_outputs
from recs.edit.record import ResolvedSource, resolve_sources
from recs.edit.render import Renderer
from recs.edit.schema import (
    CommandKind,
    EditSpec,
    SourceSpec,
    parse_edit,
    parse_partial_edit,
)
from recs.ui import session_record


class CompositionStep(EditOptions, frozen=True):
    command: str

    @field_validator('command')
    @classmethod
    def validate_command(cls, value: str) -> str:
        if not value.strip():
            raise ValueError('command must not be empty')
        return value


class ResolvedCommand(BaseModel, frozen=True):
    command: str
    recipe: dict[str, object]

    model_config = ConfigDict(extra='forbid')


class ResolvedStage(BaseModel, frozen=True):
    command: str
    operation: CommandKind
    edit: dict[str, object]

    model_config = ConfigDict(extra='forbid')


class CompositionEdit(BaseModel, frozen=True):
    schema_version: Literal[1]
    kind: Literal['composition']
    edits: list[CompositionStep] = Field(default_factory=list)
    resolved_commands: list[ResolvedCommand] = Field(default_factory=list)
    stages: list[ResolvedStage] = Field(default_factory=list)

    @model_validator(mode='after')
    def validate_resolved_lengths(self) -> Self:
        for name, values in (
            ('resolved_commands', self.resolved_commands),
            ('stages', self.stages),
        ):
            if values and len(values) != len(self.edits):
                raise ValueError(f'{name} must contain one entry per edit')
        return self

    model_config = ConfigDict(extra='forbid')


class ResolvedStep(BaseModel, frozen=True):
    step: CompositionStep
    command_path: Path
    recipe: dict[str, object]

    model_config = ConfigDict(extra='forbid')


class PreparedComposition:
    def __init__(
        self,
        canonical: CompositionEdit,
        edit: EditSpec,
        graph: EditGraph,
        rendered: dict[str, MaterializedAudio],
        stage_memory: list[int],
        peak_memory: int,
        autocalibration: autocalibrate.PreparedAutocalibrate | None = None,
    ) -> None:
        self.canonical = canonical
        self.edit = edit
        self.graph = graph
        self.rendered = rendered
        self.stage_memory = stage_memory
        self.peak_memory = peak_memory
        self.autocalibration = autocalibration


def parse_composition(text: str) -> CompositionEdit:
    return CompositionEdit.model_validate(tomlkit.parse(text))


def canonical_composition(value: CompositionEdit) -> str:
    return tomlkit.dumps(value.model_dump(mode='json', exclude_none=True))


def is_composition_file(path: Path) -> bool:
    if not path.is_file():
        return False
    return tomlkit.parse(path.read_text()).get('kind') == 'composition'


def resolve_composition(value: CompositionEdit, directory: Path) -> list[ResolvedStep]:
    result: list[ResolvedStep] = []
    embedded = value.resolved_commands or [None] * len(value.edits)
    for index, (step, resolved) in enumerate(
        zip(value.edits, embedded, strict=False), 1
    ):
        if resolved is None:
            recipe, command_path = commands.resolve_command(step.command, directory)
        else:
            if resolved.command != step.command:
                raise RecsError(
                    f'Resolved command {index} does not match edit: '
                    f'{resolved.command!r} != {step.command!r}'
                )
            recipe = resolved.recipe
            command_path = directory / step.command
        _validate_recipe(recipe, index, step.command)
        result.append(
            ResolvedStep(
                step=step,
                command_path=command_path,
                recipe={k: v for k, v in recipe.items() if k != 'extends'},
            )
        )
    return result


def prepare_composition(
    value: CompositionEdit,
    composition_path: Path,
    record_path: Path,
    destination: Path,
) -> PreparedComposition:
    record_path = _validate_record(record_path)
    resolved = resolve_composition(value, composition_path.parent)
    if not resolved:
        raise RecsError('An empty composition has no materialized result')
    if destination.exists():
        raise RecsError(f'Output composition directory already exists: {destination}')
    for index, resolved_step in enumerate(resolved[:-1], 1):
        if (
            resolved_step.step.format is not None
            or resolved_step.step.subtype is not None
        ):
            raise RecsError(
                f'Composition edit {index} requests an intermediate encoding; '
                'only the final edit may set format or subtype'
            )

    current_tracks = commands.input_tracks([record_path])
    materializer = SourceMaterializer()
    memory: dict[str, MaterializedAudio] = {}
    stages: list[ResolvedStage] = []
    stage_memory: list[int] = []
    peak_memory = 0
    final_edit: EditSpec | None = None
    final_graph: EditGraph | None = None
    final_rendered: dict[str, MaterializedAudio] = {}
    final_autocalibration: autocalibrate.PreparedAutocalibrate | None = None
    for index, resolved_step in enumerate(resolved, 1):
        operation = commands.command_operation(resolved_step.recipe)
        assert operation is not None
        if operation == CommandKind.autocalibrate:
            selected = commands.select_tracks(
                current_tracks, resolved_step.step.channel
            )
            audio, selectors = _materialize_input_tracks(selected, memory, materializer)
            sample_rates = {a.sample_rate for a in audio.values()}
            if len(sample_rates) != 1:
                raise RecsError(
                    f'Selected tracks have mixed sample rates: {sample_rates}'
                )
            sample_rate = next(iter(sample_rates))
            options = autocalibrate.AutocalibrateOptions(
                channel=selectors,
                format=resolved_step.step.format,
                subtype=resolved_step.step.subtype,
            )
            if value.stages:
                stage = value.stages[index - 1]
                if (
                    stage.command != resolved_step.step.command
                    or stage.operation != operation
                ):
                    raise RecsError(f'Resolved stage {index} does not match its edit')
                autocalibrate_edit = autocalibrate.AutocalibrateEdit.model_validate(
                    stage.edit
                )
            else:
                autocalibrate_edit = autocalibrate.autocalibrate_from_materialized(
                    f'stage-{index - 1:03d}', selectors, sample_rate, options
                )
            prepared_autocalibration = autocalibrate.prepare_materialized_autocalibrate(
                autocalibrate_edit,
                audio,
                autocalibrate.autocalibrate_track_ids(selectors),
                destination,
            )
            rendered = autocalibrate.materialized_autocalibrate_outputs(
                prepared_autocalibration
            )
            memory, materialized_session, current_tracks = _stage_session(
                index, rendered, sample_rate
            )
            stage_memory.append(
                _storage_bytes([t.audio for t in materialized_session.tracks])
            )
            peak_memory = max(peak_memory, stage_memory[-1])
            stages.append(
                ResolvedStage(
                    command=resolved_step.step.command,
                    operation=operation,
                    edit=_canonical_stage(
                        prepared_autocalibration.edit,
                        final=index == len(resolved),
                    ),
                )
            )
            final_edit = None
            final_graph = None
            final_rendered = rendered
            final_autocalibration = prepared_autocalibration
            continue
        if value.stages:
            stage = value.stages[index - 1]
            if (
                stage.command != resolved_step.step.command
                or stage.operation != operation
            ):
                raise RecsError(f'Resolved stage {index} does not match its edit')
            edit = EditSpec.model_validate(stage.edit)
        else:
            edit = commands.complete_or_generate_tracks(
                resolved_step.recipe, current_tracks, resolved_step.step
            )
        if edit.media_types != ['audio']:
            raise RecsError(
                'Compositions support only media_types = ["audio"]: '
                f'{edit.media_types}'
            )
        sources = _resolve_stage_sources(
            edit, resolved_step.command_path.parent, memory
        )
        graph = validate_graph(edit, sources)
        if index == len(resolved):
            validate_outputs(edit, graph, destination)
        canonical_edit = session.canonical_edit(edit, sources, destination)
        renderer = Renderer(canonical_edit, sources, graph, materializer)
        rendered = renderer.outputs
        memory, materialized_session, current_tracks = _stage_session(
            index, rendered, canonical_edit.sample_rate
        )
        current_bytes = _storage_bytes([t.audio for t in materialized_session.tracks])
        stage_memory.append(current_bytes)
        peak_memory = max(peak_memory, renderer.peak_memory_bytes)
        stages.append(
            ResolvedStage(
                command=resolved_step.step.command,
                operation=operation,
                edit=_canonical_stage(
                    canonical_edit,
                    final=index == len(resolved),
                ),
            )
        )
        final_edit = canonical_edit
        final_graph = graph
        final_rendered = rendered
        final_autocalibration = None
    canonical = value.model_copy(
        update={
            'resolved_commands': [
                ResolvedCommand(command=s.step.command, recipe=s.recipe)
                for s in resolved
            ],
            'stages': stages,
        }
    )
    if final_autocalibration is not None:
        placeholder = EditSpec(schema_version=1, sample_rate=sample_rate)
        placeholder_graph = EditGraph(widths={}, output_extents={}, bus_order=[])
        return PreparedComposition(
            canonical,
            placeholder,
            placeholder_graph,
            final_rendered,
            stage_memory,
            peak_memory,
            final_autocalibration,
        )
    assert final_edit is not None and final_graph is not None
    return PreparedComposition(
        canonical, final_edit, final_graph, final_rendered, stage_memory, peak_memory
    )


def execute_composition(
    value: CompositionEdit,
    composition_path: Path,
    record_path: Path,
    destination: Path | None,
) -> Path:
    record_path = _validate_record(record_path)
    if not value.edits:
        if destination is not None:
            raise RecsError('An empty composition does not create a destination')
        return record_path
    if destination is None:
        raise RecsError('A non-empty composition requires a destination')
    prepared = prepare_composition(value, composition_path, record_path, destination)
    metadata = {
        'source_record': record_path.as_posix(),
        'peak_memory_bytes': prepared.peak_memory,
    }
    if prepared.autocalibration is not None:
        return autocalibrate.write_autocalibrate_session(
            prepared.autocalibration,
            destination,
            canonical_composition(prepared.canonical),
            metadata,
        )
    return session.write_session(
        canonical_composition(prepared.canonical),
        prepared.edit,
        prepared.graph,
        prepared.rendered,
        destination,
        metadata,
    )


def composition_summary(
    value: CompositionEdit,
    composition_path: Path,
    record_path: Path,
    destination: Path | None,
) -> str:
    record_path = _validate_record(record_path)
    if not value.edits:
        if destination is not None:
            raise RecsError('An empty composition does not create a destination')
        return f'Record: {record_path}\nEdits: none\nResult: {record_path}\n'
    if destination is None:
        raise RecsError('A non-empty composition requires a destination')
    prepared = prepare_composition(value, composition_path, record_path, destination)
    lines = [
        f'Record: {record_path}',
        f'Output session: {destination}',
        'Intermediate media: memory only',
    ]
    for index, (step, size) in enumerate(
        zip(value.edits, prepared.stage_memory, strict=False), 1
    ):
        selectors = ', '.join(step.channel) or 'all compatible tracks'
        lines.append(f'{index}: {step.command}')
        lines.append(f'   Selectors: {selectors}')
        lines.append(f'   Materialized audio: {size} bytes')
    lines.append(f'Estimated peak materialized audio: {prepared.peak_memory} bytes')
    lines.append(f'Result: {destination / "session-record.jsonl"}')
    return '\n'.join(lines) + '\n'


def _canonical_stage(
    edit: EditSpec | autocalibrate.AutocalibrateEdit, *, final: bool
) -> dict[str, object]:
    if final:
        return edit.model_dump(mode='json', exclude_none=True)
    if isinstance(edit, autocalibrate.AutocalibrateEdit):
        edit = edit.model_copy(
            update={
                'output': edit.output.model_copy(
                    update={'format': None, 'subtype': None}
                )
            }
        )
    else:
        edit = edit.model_copy(
            update={
                'outputs': [
                    o.model_copy(update={'path': None, 'format': None, 'subtype': None})
                    for o in edit.outputs
                ]
            }
        )
    return edit.model_dump(mode='json', exclude_none=True)


def _validate_recipe(recipe: dict[str, object], index: int, command: str) -> None:
    text = tomlkit.dumps(recipe)
    try:
        parse_edit(text)
    except ValueError:
        partial = parse_partial_edit(text)
        if partial.command is None or partial.command.operation is None:
            raise RecsError(
                f'Composite child {index} has no _command.operation: {command}'
            ) from None
    else:
        raise RecsError(
            f'Composite child {index} is a complete arrangement and does not '
            f'consume its input session: {command}'
        )


def _resolve_stage_sources(
    edit: EditSpec, directory: Path, memory: Mapping[str, MaterializedAudio]
) -> dict[str, ResolvedSource | MaterializedAudio]:
    disk = [s for s in edit.sources if s.memory is None]
    result: dict[str, ResolvedSource | MaterializedAudio] = {}
    if disk:
        result.update(
            resolve_sources(edit.model_copy(update={'sources': disk}), directory)
        )
    for source in edit.sources:
        if source.memory is None:
            continue
        try:
            audio = memory[source.memory]
        except KeyError:
            raise RecsError(
                f'Source {source.id}: unknown materialized track {source.memory}'
            ) from None
        result[source.id] = select_channels(audio, source.channels)
    return result


def _stage_session(
    index: int,
    rendered: dict[str, MaterializedAudio],
    sample_rate: int,
) -> tuple[
    dict[str, MaterializedAudio], MaterializedSession, list[commands.InputTrack]
]:
    memory: dict[str, MaterializedAudio] = {}
    tracks: list[MaterializedTrack] = []
    inputs: list[commands.InputTrack] = []
    for track_name, audio in rendered.items():
        key = f'stage-{index:03d}:{track_name}'
        memory[key] = audio
        tracks.append(
            MaterializedTrack(
                source='edit',
                track_name=track_name,
                stream_id=f'audio:edit:{track_name}',
                audio=audio,
            )
        )
        label = f'edit:{track_name}'
        inputs.append(
            commands.InputTrack(
                label=label,
                selectors=[label],
                source=SourceSpec(
                    id='source',
                    memory=key,
                    channels=list(range(1, audio.channels + 1)),
                ),
                channels=audio.channels,
                sample_rate=sample_rate,
                frame_count=audio.end_frame,
            )
        )
    materialized_session = MaterializedSession(
        session_id=f'stage-{index:03d}',
        duration_frames=max((a.end_frame for a in rendered.values()), default=0),
        tracks=tracks,
    )
    return memory, materialized_session, inputs


def _materialize_input_tracks(
    tracks: list[commands.InputTrack],
    memory: Mapping[str, MaterializedAudio],
    materializer: SourceMaterializer,
) -> tuple[dict[str, MaterializedAudio], list[str]]:
    if not tracks:
        raise RecsError('Autocalibration requires at least one input track')
    edit = EditSpec(
        schema_version=1,
        sample_rate=tracks[0].sample_rate,
        sources=[
            t.source.model_copy(update={'id': f'source-{i}'})
            for i, t in enumerate(tracks)
        ],
    )
    resolved = _resolve_stage_sources(edit, Path.cwd(), memory)
    audio: dict[str, MaterializedAudio] = {}
    for index, track in enumerate(tracks):
        value = resolved[f'source-{index}']
        audio[track.label] = (
            value
            if isinstance(value, MaterializedAudio)
            else materializer.materialize(value)
        )
    return audio, [t.label for t in tracks]


def _storage_bytes(values: list[MaterializedAudio]) -> int:
    arrays: dict[int, np.ndarray] = {}
    for value in values:
        array = value.samples
        while isinstance(array.base, np.ndarray):
            array = array.base
        arrays[id(array)] = array
    return sum(a.nbytes for a in arrays.values())


def _validate_record(path: Path) -> Path:
    path = path.resolve()
    if not path.is_file():
        raise RecsError(f'Session record does not exist: {path}')
    entries, errors = session_record.read_entries(path)
    if errors:
        raise RecsError('; '.join(errors))
    if not entries or not isinstance(entries[0], session_record.SessionHeader):
        raise RecsError(f'Session record has no initial header: {path}')
    return path
