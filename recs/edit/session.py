import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

import soundfile
from pydantic import BaseModel, ConfigDict

from recs.base.errors import RecsError
from recs.edit.graph import EditGraph, validate_graph
from recs.edit.output import bit_depth, validate_outputs
from recs.edit.record import ResolvedSource, resolve_sources
from recs.edit.render import Renderer
from recs.edit.schema import EditSpec, canonical_toml
from recs.ui import session_record


class PreparedEdit(BaseModel, frozen=True):
    edit: EditSpec
    sources: dict[str, ResolvedSource]
    graph: EditGraph

    model_config = ConfigDict(extra='forbid')


def prepare_edit(
    edit: EditSpec, edit_directory: Path, destination: Path
) -> PreparedEdit:
    if len(edit.media_types) != 1 or edit.media_types[0] != 'audio':
        raise RecsError(
            f'This editor supports only media_types = ["audio"]: {edit.media_types}'
        )
    sources = resolve_sources(edit, edit_directory)
    graph = validate_graph(edit, sources)
    validate_outputs(edit, graph, destination)
    canonical = _canonical_edit(edit, sources, destination)
    return PreparedEdit(edit=canonical, sources=sources, graph=graph)


def execute_edit(edit: EditSpec, edit_directory: Path, destination: Path) -> Path:
    prepared = prepare_edit(edit, edit_directory, destination)
    canonical = prepared.edit
    sources = prepared.sources
    graph = prepared.graph

    destination.mkdir(parents=True)
    edit_path = destination / 'edit.toml'
    edit_path.write_text(canonical_toml(canonical))
    now = datetime.now(timezone.utc)
    writer = session_record.SessionRecordWriter(
        destination / 'session-record.jsonl',
        started_at=_timestamp(now),
        session_id=str(uuid.uuid4()),
        application={'name': 'recs edit'},
    )
    writer.write(
        session_record.EventRecord(
            type='edit_started',
            timestamp=_timestamp(now),
            path='edit.toml',
            metadata=_resolution_metadata(sources, graph),
        ),
        sync=True,
    )
    renderer = Renderer(canonical, sources, graph)
    try:
        for output in canonical.outputs:
            path = destination / output.path
            stream_id = f'audio:edit:{output.id}'
            frame_range = graph.output_extents[output.id]
            channels = graph.widths[output.source]
            started = session_record.FileRecord(
                type='file_started',
                media_type='audio',
                timestamp=_timestamp(datetime.now(timezone.utc)),
                stream_id=stream_id,
                format=output.format,
                frame_count=frame_range.start,
                path=output.path.as_posix(),
                source='edit',
                track_name=output.id,
                source_channels=list(range(1, channels + 1)),
                channels=channels,
                sample_rate=canonical.sample_rate,
            )
            writer.write(started)
            quantity = renderer.render_output(output, path)
            with soundfile.SoundFile(path) as fp:
                depth = bit_depth(fp)
            writer.write(
                started.model_copy(
                    update={
                        'type': 'file_finished',
                        'timestamp': _timestamp(datetime.now(timezone.utc)),
                        'frame_count': frame_range.end,
                        'quantity_count': quantity,
                        'bit_depth': depth,
                    }
                )
            )
    except (OSError, RecsError, soundfile.SoundFileError, KeyboardInterrupt) as e:
        message = 'Edit interrupted' if isinstance(e, KeyboardInterrupt) else str(e)
        try:
            writer.write(
                session_record.WarningRecord(
                    timestamp=_timestamp(datetime.now(timezone.utc)), message=message
                ),
                sync=True,
            )
        except OSError:
            pass
        finally:
            writer.close()
        raise
    ended = datetime.now(timezone.utc)
    writer.write(
        session_record.SessionFooter(
            ended_at=_timestamp(ended), duration_seconds=(ended - now).total_seconds()
        ),
        sync=True,
    )
    writer.close()
    return writer.path


def _canonical_edit(
    edit: EditSpec, sources: dict[str, ResolvedSource], destination: Path
) -> EditSpec:
    replacements = []
    for source in edit.sources:
        record = sources[source.id].record
        try:
            value = Path(os.path.relpath(record, destination))
        except ValueError:
            value = record
        replacements.append(source.model_copy(update={'record': value}))
    return edit.model_copy(update={'sources': replacements})


def _resolution_metadata(
    sources: dict[str, ResolvedSource], graph: EditGraph
) -> dict[str, object]:
    return {
        'sources': {
            s.id: {
                'session_id': s.session_id,
                'files': [f.path.as_posix() for f in s.fragments],
            }
            for s in sources.values()
        },
        'output_ranges': {
            k: {'start': v.start, 'end': v.end} for k, v in graph.output_extents.items()
        },
    }


def _timestamp(value: datetime) -> str:
    return value.isoformat(timespec='milliseconds').replace('+00:00', 'Z')
