import os
import uuid
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path

import soundfile
from pydantic import BaseModel, ConfigDict
from ufor.arrangement import ArrangementScore
from ufor.codec import score_toml
from ufor.interface import OutputSelection
from ufor.recording import RecordingScore

from recs.base.errors import RecsError
from recs.edit.graph import EditGraph, validate_graph
from recs.edit.materialized import MaterializedAudio
from recs.edit.nested import resolve_sources
from recs.edit.output import bit_depth, open_output, validate_outputs
from recs.edit.record import ResolvedSource
from recs.edit.render import Renderer
from recs.recording.finalize import finalize_recording
from recs.ui import session_record


class PreparedEdit(BaseModel, frozen=True):
    edit: ArrangementScore
    sources: dict[OutputSelection, ResolvedSource | MaterializedAudio]
    graph: EditGraph

    model_config = ConfigDict(extra='forbid', arbitrary_types_allowed=True)


def prepare_edit(
    edit: ArrangementScore,
    edit_directory: Path,
    destination: Path,
    supplied: dict[Path, RecordingScore] | None = None,
) -> PreparedEdit:
    if len(edit.body.media_types) != 1 or edit.body.media_types[0] != 'audio':
        raise RecsError(
            'This editor supports only media_types = ["audio"]: '
            f'{edit.body.media_types}'
        )
    sources = resolve_sources(edit, edit_directory, supplied)
    graph = validate_graph(edit, sources)
    validate_outputs(edit, graph, destination)
    canonical = canonical_edit(edit, sources, destination, edit_directory)
    return PreparedEdit(edit=canonical, sources=sources, graph=graph)


def execute_edit(
    edit: ArrangementScore, edit_directory: Path, destination: Path
) -> Path:
    prepared = prepare_edit(edit, edit_directory, destination)
    canonical = prepared.edit
    rendered = Renderer(canonical, prepared.sources, prepared.graph).outputs
    return write_session(
        score_toml(canonical),
        canonical,
        prepared.graph,
        rendered,
        destination,
        _resolution_metadata(prepared.sources, prepared.graph),
    )


def write_session(
    edit_text: str,
    edit: ArrangementScore,
    graph: EditGraph,
    rendered: dict[str, MaterializedAudio],
    destination: Path,
    metadata: dict[str, object],
) -> Path:
    destination.mkdir(parents=True)
    edit_path = destination / 'edit.toml'
    edit_path.write_text(edit_text)
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
            metadata=metadata,
        ),
        sync=True,
    )
    try:
        destinations = {d.output: d for d in edit.destinations}
        for output in edit.outputs:
            target = destinations[output.name]
            path = destination / target.path
            stream_id = f'audio:edit:{output.name}'
            frame_range = graph.output_extents[output.name]
            channels = rendered[output.name].channels
            started = session_record.AudioFileRecord(
                clock_id=edit.timebases[0].name,
                type='file_started',
                media_type='audio',
                timestamp=_timestamp(datetime.now(timezone.utc)),
                stream_id=stream_id,
                format=target.format,
                frame_count=frame_range.start,
                path=target.path.as_posix(),
                source='edit',
                track_name=output.name,
                source_channels=list(range(1, channels + 1)),
                channels=channels,
                sample_rate=edit.timebases[0].rate.numerator,
            )
            writer.write(started)
            audio = rendered[output.name]
            fp = open_output(
                target,
                path,
                audio.channels,
                audio.sample_rate,
            )
            try:
                fp.write(audio.samples)
            finally:
                fp.close()
            quantity = len(audio.samples)
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
    return finalize_recording(writer.path)


def canonical_edit(
    edit: ArrangementScore,
    sources: Mapping[OutputSelection, ResolvedSource | MaterializedAudio],
    destination: Path,
    origin: Path,
) -> ArrangementScore:
    replacements = []
    for node in edit.body.parts:
        if node.score.path.startswith('prepared/'):
            replacements.append(node)
            continue
        reference = node.score.model_copy(
            update={
                'path': os.path.relpath(
                    (origin / node.score.path).resolve(), destination
                )
            }
        )
        node = node.model_copy(update={'score': reference})
        replacements.append(node)
    return edit.model_copy(
        update={'body': edit.body.model_copy(update={'parts': replacements})}
    )


def _resolution_metadata(
    sources: dict[OutputSelection, ResolvedSource | MaterializedAudio], graph: EditGraph
) -> dict[str, object]:
    return {
        'sources': {
            s.name if isinstance(s, ResolvedSource) else f'{a.name}/{a.output}': (
                {
                    'session_id': s.session_id,
                    'files': [f.path.as_posix() for f in s.fragments],
                }
                if isinstance(s, ResolvedSource)
                else {
                    'start': s.start_frame,
                    'end': s.end_frame,
                    'sample_rate': s.sample_rate,
                }
            )
            for a, s in sources.items()
        },
        'output_ranges': {
            k: {'start': v.start, 'end': v.end} for k, v in graph.output_extents.items()
        },
    }


def _timestamp(value: datetime) -> str:
    return value.isoformat(timespec='milliseconds').replace('+00:00', 'Z')
