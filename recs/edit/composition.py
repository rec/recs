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
    Identifier,
    SourceSpec,
    identifier,
    parse_edit,
    parse_partial_edit,
)
from recs.ui import session_record

ROOT_NODE = 'root'


class ResolvedNode(BaseModel, frozen=True):
    recipe: dict[str, object]

    operation: CommandKind

    edit: dict[str, object]

    model_config = ConfigDict(extra='forbid')


class CompositionStep(EditOptions, frozen=True):
    id: Identifier

    command: str

    inputs: list[str] = Field(min_length=1)

    resolved: ResolvedNode | None = None

    @field_validator('command')
    @classmethod
    def validate_command(cls, value: str) -> str:
        if not value.strip():
            raise ValueError('command must not be empty')
        return value

    @field_validator('inputs')
    @classmethod
    def validate_inputs(cls, values: list[str]) -> list[str]:
        if len(values) != len(set(values)):
            raise ValueError('inputs must not contain duplicates')
        for value in values:
            if value != ROOT_NODE:
                identifier(value)
        return values


class CompositionEdit(BaseModel, frozen=True):
    schema_version: Literal[2]

    kind: Literal['composition']

    result: str

    edits: list[CompositionStep] = Field(default_factory=list)

    @model_validator(mode='after')
    def validate_edit_graph(self) -> Self:
        _composition_order(self.edits, self.result)
        return self

    model_config = ConfigDict(extra='forbid')


class ResolvedStep(BaseModel, frozen=True):
    step: CompositionStep

    command_path: Path

    recipe: dict[str, object]

    operation: CommandKind

    model_config = ConfigDict(extra='forbid')


class PreparedComposition:
    def __init__(
        self,
        canonical: CompositionEdit,
        edit: EditSpec,
        graph: EditGraph,
        rendered: dict[str, MaterializedAudio],
        node_memory: dict[str, int],
        peak_memory: int,
        execution_order: list[str],
        autocalibration: autocalibrate.PreparedAutocalibrate | None = None,
    ) -> None:
        self.canonical = canonical
        self.edit = edit
        self.graph = graph
        self.rendered = rendered
        self.node_memory = node_memory
        self.peak_memory = peak_memory
        self.execution_order = execution_order
        self.autocalibration = autocalibration


class AudioDescription(BaseModel, frozen=True):
    channels: int

    timeline_end: int

    model_config = ConfigDict(extra='forbid')


class CompiledNode(BaseModel, frozen=True):
    resolved: ResolvedStep

    edit: EditSpec | autocalibrate.AutocalibrateEdit

    graph: EditGraph | None

    disk_sources: dict[str, ResolvedSource]

    selected_tracks: list[commands.InputTrack]

    model_config = ConfigDict(extra='forbid')


def parse_composition(text: str) -> CompositionEdit:
    return CompositionEdit.model_validate(tomlkit.parse(text))


def canonical_composition(value: CompositionEdit) -> str:
    return tomlkit.dumps(value.model_dump(mode='json', exclude_none=True))


def is_composition_file(path: Path) -> bool:
    if not path.is_file():
        return False
    return tomlkit.parse(path.read_text()).get('kind') == 'composition'


def resolve_composition(value: CompositionEdit, directory: Path) -> list[ResolvedStep]:
    steps = {s.id: s for s in value.edits}
    result: list[ResolvedStep] = []
    for node_id in _composition_order(value.edits, value.result):
        step = steps[node_id]
        if step.resolved is None:
            recipe, command_path = commands.resolve_command(step.command, directory)
            _validate_recipe(recipe, node_id, step.command)
            operation = commands.command_operation(recipe)
            if operation is None:
                raise RecsError(
                    f'Composition node {node_id!r} has no _command.operation'
                )
        else:
            recipe = step.resolved.recipe
            command_path = directory / step.command
            _validate_recipe(recipe, node_id, step.command)
            operation = commands.command_operation(recipe)
            if operation != step.resolved.operation:
                raise RecsError(
                    f'Composition node {node_id!r} resolved operation does not '
                    'match its recipe'
                )
        assert operation is not None
        result.append(
            ResolvedStep(
                step=step,
                command_path=command_path,
                recipe={k: v for k, v in recipe.items() if k != 'extends'},
                operation=operation,
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
    for resolved_step in resolved:
        step = resolved_step.step
        if step.id != value.result and (
            step.format is not None or step.subtype is not None
        ):
            raise RecsError(
                f'Composition node {step.id!r} requests an intermediate encoding; '
                'only the result node may set format or subtype'
            )

    root_tracks = _namespace_tracks(ROOT_NODE, commands.input_tracks([record_path]))
    compiled_nodes = _compile_nodes(resolved, value.result, root_tracks, destination)
    sessions: dict[str, list[commands.InputTrack]] = {ROOT_NODE: root_tracks}
    materializer = SourceMaterializer()
    memory: dict[str, MaterializedAudio] = {}
    consumers = _consumer_counts(value.edits)
    canonical_steps: list[CompositionStep] = []
    node_memory: dict[str, int] = {}
    peak_memory = 0
    final_edit: EditSpec | None = None
    final_graph: EditGraph | None = None
    final_rendered: dict[str, MaterializedAudio] = {}
    final_autocalibration: autocalibrate.PreparedAutocalibrate | None = None
    final_sample_rate = 0

    for compiled in compiled_nodes:
        resolved_step = compiled.resolved
        step = resolved_step.step
        live_before = _live_storage(materializer, memory)
        if resolved_step.operation == CommandKind.autocalibrate:
            audio, selectors = _materialize_input_tracks(
                compiled.selected_tracks, memory, materializer
            )
            autocalibrate_edit = compiled.edit
            assert isinstance(autocalibrate_edit, autocalibrate.AutocalibrateEdit)
            assert autocalibrate_edit.sample_rate is not None
            node_sample_rate = autocalibrate_edit.sample_rate
            prepared_autocalibration = autocalibrate.prepare_materialized_autocalibrate(
                autocalibrate_edit,
                audio,
                autocalibrate.autocalibrate_track_ids(selectors),
                destination,
            )
            rendered = autocalibrate.materialized_autocalibrate_outputs(
                prepared_autocalibration
            )
            canonical_edit = _canonical_stage(
                prepared_autocalibration.edit, final=step.id == value.result
            )
            graph = None
            peak_memory = max(
                peak_memory,
                live_before + _storage_bytes(list(rendered.values())),
            )
            if step.id == value.result:
                final_autocalibration = prepared_autocalibration
                final_edit = None
                final_graph = None
                final_rendered = rendered
                final_sample_rate = node_sample_rate
        else:
            edit = compiled.edit
            graph = compiled.graph
            assert isinstance(edit, EditSpec) and graph is not None
            sources = _runtime_sources(edit, compiled.disk_sources, memory)
            canonical = session.canonical_edit(edit, sources, destination)
            node_sample_rate = canonical.sample_rate
            renderer = Renderer(canonical, sources, graph, materializer)
            rendered = renderer.outputs
            canonical_edit = _canonical_stage(canonical, final=step.id == value.result)
            peak_memory = max(peak_memory, live_before + renderer.peak_memory_bytes)
            if step.id == value.result:
                final_edit = canonical
                final_graph = graph
                final_rendered = rendered
                final_autocalibration = None
                final_sample_rate = node_sample_rate

        node_audio, materialized_session, node_tracks = _node_session(
            step.id, rendered, node_sample_rate
        )
        memory.update(node_audio)
        sessions[step.id] = node_tracks
        node_memory[step.id] = _storage_bytes(
            [t.audio for t in materialized_session.tracks]
        )
        peak_memory = max(peak_memory, _live_storage(materializer, memory))
        canonical_steps.append(
            step.model_copy(
                update={
                    'resolved': ResolvedNode(
                        recipe=resolved_step.recipe,
                        operation=resolved_step.operation,
                        edit=canonical_edit,
                    )
                }
            )
        )
        for input_id in step.inputs:
            consumers[input_id] -= 1
            if consumers[input_id] == 0:
                _release_node(input_id, sessions, memory, materializer)

    canonical = CompositionEdit(
        schema_version=2,
        kind='composition',
        result=value.result,
        edits=canonical_steps,
    )
    execution_order = [s.step.id for s in resolved]
    if final_autocalibration is not None:
        placeholder = EditSpec(schema_version=1, sample_rate=final_sample_rate)
        placeholder_graph = EditGraph(widths={}, output_extents={}, bus_order=[])
        return PreparedComposition(
            canonical,
            placeholder,
            placeholder_graph,
            final_rendered,
            node_memory,
            peak_memory,
            execution_order,
            final_autocalibration,
        )
    assert final_edit is not None and final_graph is not None
    return PreparedComposition(
        canonical,
        final_edit,
        final_graph,
        final_rendered,
        node_memory,
        peak_memory,
        execution_order,
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
        'execution_order': prepared.execution_order,
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
    steps = {s.id: s for s in value.edits}
    lines = [
        f'Record: {record_path}',
        f'Result node: {value.result}',
        f'Output session: {destination}',
        'Intermediate media: memory only',
        f'Execution order: {", ".join(prepared.execution_order)}',
    ]
    for node_id in prepared.execution_order:
        step = steps[node_id]
        selectors = ', '.join(step.channel) or 'all compatible tracks'
        lines.append(f'{node_id}: {step.command}')
        lines.append(f'   Inputs: {", ".join(step.inputs)}')
        lines.append(f'   Selectors: {selectors}')
        lines.append(f'   Materialized audio: {prepared.node_memory[node_id]} bytes')
    lines.append(f'Estimated peak materialized audio: {prepared.peak_memory} bytes')
    lines.append(f'Result: {destination / "session-record.jsonl"}')
    return '\n'.join(lines) + '\n'


def _composition_order(edits: list[CompositionStep], result: str) -> list[str]:
    ids = [e.id for e in edits]
    if len(ids) != len(set(ids)):
        raise ValueError('composition edit IDs must be unique')
    if ROOT_NODE in ids:
        raise ValueError(f'{ROOT_NODE!r} is reserved for the original session')
    if not edits:
        if result != ROOT_NODE:
            raise ValueError('an empty composition must use result = "root"')
        return []
    identifier(result)
    if result not in ids:
        raise ValueError(f'unknown composition result: {result}')
    known = set(ids) | {ROOT_NODE}
    for edit in edits:
        unknown = sorted(set(edit.inputs) - known)
        if unknown:
            raise ValueError(
                f'composition node {edit.id!r} has unknown inputs: {unknown}'
            )
        if edit.id in edit.inputs:
            raise ValueError(f'composition node {edit.id!r} depends on itself')

    dependencies = {e.id: set(e.inputs) - {ROOT_NODE} for e in edits}
    remaining = set(ids)
    order: list[str] = []
    while remaining:
        ready = sorted(i for i in remaining if dependencies[i] <= set(order))
        if not ready:
            raise ValueError('composition graph contains a cycle')
        order.extend(ready)
        remaining.difference_update(ready)

    ancestors = {result}
    pending = [result]
    while pending:
        for node_id in dependencies[pending.pop()]:
            if node_id not in ancestors:
                ancestors.add(node_id)
                pending.append(node_id)
    disconnected = sorted(set(ids) - ancestors)
    if disconnected:
        raise ValueError(
            f'composition nodes do not contribute to result: {disconnected}'
        )
    return order


def _compile_nodes(
    resolved: list[ResolvedStep],
    result_node: str,
    root_tracks: list[commands.InputTrack],
    destination: Path,
) -> list[CompiledNode]:
    inventories: dict[str, list[commands.InputTrack]] = {ROOT_NODE: root_tracks}
    memory_tracks: dict[str, commands.InputTrack] = {}
    result: list[CompiledNode] = []
    for resolved_step in resolved:
        step = resolved_step.step
        input_tracks = [t for i in step.inputs for t in inventories[i]]
        if resolved_step.operation == CommandKind.autocalibrate:
            selected = commands.select_tracks(input_tracks, step.channel)
            sample_rates = {t.sample_rate for t in selected}
            if len(sample_rates) != 1:
                raise RecsError(
                    f'Selected tracks have mixed sample rates: {sample_rates}'
                )
            sample_rate = next(iter(sample_rates))
            selectors = [t.label for t in selected]
            options = autocalibrate.AutocalibrateOptions(
                channel=selectors,
                format=step.format,
                subtype=step.subtype,
            )
            edit = (
                autocalibrate.autocalibrate_from_materialized(
                    step.id, selectors, sample_rate, options
                )
                if step.resolved is None
                else autocalibrate.AutocalibrateEdit.model_validate(step.resolved.edit)
            )
            if edit.sample_rate != sample_rate:
                raise RecsError(
                    f'Composition node {step.id!r} uses sample rate '
                    f'{edit.sample_rate}, but its inputs use {sample_rate}'
                )
            output_tracks = _autocalibration_output_tracks(
                step.id,
                selected,
                autocalibrate.autocalibrate_track_ids(selectors),
            )
            compiled = CompiledNode(
                resolved=resolved_step,
                edit=edit,
                graph=None,
                disk_sources={},
                selected_tracks=selected,
            )
        else:
            edit = (
                commands.complete_or_generate_tracks(
                    resolved_step.recipe, input_tracks, step
                )
                if step.resolved is None
                else EditSpec.model_validate(step.resolved.edit)
            )
            if edit.media_types != ['audio']:
                raise RecsError(
                    'Compositions support only media_types = ["audio"]: '
                    f'{edit.media_types}'
                )
            disk_sources, descriptions = _described_sources(
                edit, resolved_step.command_path.parent, memory_tracks
            )
            graph = validate_graph(edit, descriptions)
            if step.id == result_node:
                validate_outputs(edit, graph, destination)
            output_tracks = _output_tracks(step.id, edit, graph)
            compiled = CompiledNode(
                resolved=resolved_step,
                edit=edit,
                graph=graph,
                disk_sources=disk_sources,
                selected_tracks=input_tracks,
            )
        inventories[step.id] = output_tracks
        memory_tracks.update(
            {t.source.memory: t for t in output_tracks if t.source.memory is not None}
        )
        result.append(compiled)
    return result


def _described_sources(
    edit: EditSpec,
    directory: Path,
    memory_tracks: Mapping[str, commands.InputTrack],
) -> tuple[dict[str, ResolvedSource], dict[str, ResolvedSource | AudioDescription]]:
    disk = [s for s in edit.sources if s.memory is None]
    disk_sources = (
        resolve_sources(edit.model_copy(update={'sources': disk}), directory)
        if disk
        else {}
    )
    result: dict[str, ResolvedSource | AudioDescription] = dict(disk_sources)
    for source in edit.sources:
        if source.memory is None:
            continue
        try:
            track = memory_tracks[source.memory]
        except KeyError:
            raise RecsError(
                f'Source {source.id}: unknown materialized track {source.memory}'
            ) from None
        if source.channels[-1] > track.channels:
            raise RecsError(
                f'Source {source.id}: channel {source.channels[-1]} exceeds '
                f'materialized width {track.channels}'
            )
        if track.sample_rate != edit.sample_rate:
            raise RecsError(
                f'Edit sample rate is {edit.sample_rate}, but source {source.id} '
                f'uses {track.sample_rate}'
            )
        result[source.id] = AudioDescription(
            channels=len(source.channels), timeline_end=track.frame_count
        )
    return disk_sources, result


def _output_tracks(
    node_id: str, edit: EditSpec, graph: EditGraph
) -> list[commands.InputTrack]:
    return [
        commands.InputTrack(
            label=f'{node_id}:{output.id}',
            selectors=[f'{node_id}:{output.id}'],
            source=SourceSpec(
                id='source',
                memory=f'{node_id}:{output.id}',
                channels=list(range(1, graph.widths[output.source] + 1)),
            ),
            channels=graph.widths[output.source],
            sample_rate=edit.sample_rate,
            frame_count=graph.output_extents[output.id].end,
        )
        for output in edit.outputs
    ]


def _autocalibration_output_tracks(
    node_id: str,
    selected: list[commands.InputTrack],
    track_ids: dict[str, str],
) -> list[commands.InputTrack]:
    return [
        commands.InputTrack(
            label=f'{node_id}:{track_ids[track.label]}',
            selectors=[f'{node_id}:{track_ids[track.label]}'],
            source=SourceSpec(
                id='source',
                memory=f'{node_id}:{track_ids[track.label]}',
                channels=list(range(1, track.channels + 1)),
            ),
            channels=track.channels,
            sample_rate=track.sample_rate,
            frame_count=track.frame_count,
        )
        for track in selected
    ]


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


def _validate_recipe(recipe: dict[str, object], node_id: str, command: str) -> None:
    text = tomlkit.dumps(recipe)
    try:
        parse_edit(text)
    except ValueError:
        partial = parse_partial_edit(text)
        if partial.command is None or partial.command.operation is None:
            raise RecsError(
                f'Composition node {node_id!r} has no _command.operation: {command}'
            ) from None
    else:
        raise RecsError(
            f'Composition node {node_id!r} is a complete arrangement and does not '
            f'consume its input session: {command}'
        )


def _runtime_sources(
    edit: EditSpec,
    disk_sources: Mapping[str, ResolvedSource],
    memory: Mapping[str, MaterializedAudio],
) -> dict[str, ResolvedSource | MaterializedAudio]:
    result: dict[str, ResolvedSource | MaterializedAudio] = dict(disk_sources)
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


def _node_session(
    node_id: str,
    rendered: dict[str, MaterializedAudio],
    sample_rate: int,
) -> tuple[
    dict[str, MaterializedAudio], MaterializedSession, list[commands.InputTrack]
]:
    memory: dict[str, MaterializedAudio] = {}
    tracks: list[MaterializedTrack] = []
    inputs: list[commands.InputTrack] = []
    for track_name, audio in rendered.items():
        key = f'{node_id}:{track_name}'
        memory[key] = audio
        tracks.append(
            MaterializedTrack(
                source=node_id,
                track_name=track_name,
                stream_id=f'audio:{node_id}:{track_name}',
                audio=audio,
            )
        )
        inputs.append(
            commands.InputTrack(
                label=key,
                selectors=[key],
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
        session_id=node_id,
        duration_frames=max((a.end_frame for a in rendered.values()), default=0),
        tracks=tracks,
    )
    return memory, materialized_session, inputs


def _namespace_tracks(
    node_id: str, tracks: list[commands.InputTrack]
) -> list[commands.InputTrack]:
    result: list[commands.InputTrack] = []
    for track in tracks:
        label = f'{node_id}:{track.label}'
        result.append(track.model_copy(update={'label': label, 'selectors': [label]}))
    return result


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
    disk = [s for s in edit.sources if s.memory is None]
    disk_sources = (
        resolve_sources(edit.model_copy(update={'sources': disk}), Path.cwd())
        if disk
        else {}
    )
    resolved = _runtime_sources(edit, disk_sources, memory)
    audio: dict[str, MaterializedAudio] = {}
    for index, track in enumerate(tracks):
        value = resolved[f'source-{index}']
        audio[track.label] = (
            value
            if isinstance(value, MaterializedAudio)
            else materializer.materialize(value)
        )
    return audio, [t.label for t in tracks]


def _consumer_counts(edits: list[CompositionStep]) -> dict[str, int]:
    result = {ROOT_NODE: 0} | {e.id: 0 for e in edits}
    for edit in edits:
        for input_id in edit.inputs:
            result[input_id] += 1
    return result


def _release_node(
    node_id: str,
    sessions: dict[str, list[commands.InputTrack]],
    memory: dict[str, MaterializedAudio],
    materializer: SourceMaterializer,
) -> None:
    tracks = sessions.pop(node_id, [])
    for track in tracks:
        if track.source.memory is not None:
            memory.pop(track.source.memory, None)
    if node_id == ROOT_NODE:
        materializer.audio.clear()


def _live_storage(
    materializer: SourceMaterializer, memory: Mapping[str, MaterializedAudio]
) -> int:
    return _storage_bytes(list(materializer.audio.values()) + list(memory.values()))


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
