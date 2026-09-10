"""Host loading and realization of portable recording and arrangement graphs."""

from hashlib import sha256
from pathlib import Path

from ufor.arrangement import ArrangementScore
from ufor.codec import parse_score, score_toml
from ufor.composition import Composition, ScoreRecord
from ufor.interface import (
    OutputSelection,
    StreamBinding,
)
from ufor.recording import AudioStream, RecordingScore
from ufor.references import RecordSelector

from recs.base.errors import RecsError
from recs.edit.inputs import SourceSpec
from recs.edit.materialized import MaterializedAudio
from recs.edit.record import ResolvedSource, resolve_input


def load_composition(
    edit: ArrangementScore,
    directory: Path,
    package_root: Path | None = None,
    supplied: dict[Path, RecordingScore] | None = None,
) -> Composition:
    root = directory.resolve()
    records: dict[str, ScoreRecord] = {}
    active: set[Path] = set()

    def load(path: Path) -> str:
        path = path.resolve()
        if package_root is not None and not path.is_relative_to(package_root.resolve()):
            raise RecsError(f'ScoreVersion escapes package root: {path}')
        identity = str(path)
        if path in active:
            raise RecsError(f'ScoreVersion cycle: {path}')
        if identity in records:
            return identity
        active.add(path)
        if supplied is not None and path in supplied:
            score = supplied[path]
            data = score_toml(score).encode()
        else:
            data = path.read_bytes()
            score = parse_score(data.decode())
        links = {}
        if isinstance(score, ArrangementScore):
            links = {
                n.score.path: load(path.parent / n.score.path) for n in score.body.parts
            }
        records[identity] = ScoreRecord(
            score=score, paths=links, sha256=sha256(data).hexdigest()
        )
        active.remove(path)
        return identity

    links = {n.score.path: load(root / n.score.path) for n in edit.body.parts}
    records['root'] = ScoreRecord(score=edit, paths=links)
    return Composition('root', records)


def resolve_sources(
    edit: ArrangementScore,
    edit_directory: Path,
    supplied: dict[Path, RecordingScore] | None = None,
) -> dict[OutputSelection, ResolvedSource | MaterializedAudio]:
    from recs.edit.graph import validate_graph
    from recs.edit.render import Renderer

    composition = load_composition(edit, edit_directory, supplied=supplied)
    if edit.inputs:
        raise RecsError('offline audio rendering requires supplied root inputs')
    realized: dict[str, dict[str, MaterializedAudio]] = {}

    def source(path: str, port_name: str) -> ResolvedSource | MaterializedAudio:
        part = composition.parts[path]
        score = composition.scores[part.score].score
        port = composition.output(path, port_name)
        if isinstance(port.binding, OutputSelection):
            return source(part.children[port.binding.name], port.binding.output)
        if isinstance(score, RecordingScore) and isinstance(
            port.binding, StreamBinding
        ):
            stream = next(
                s for s in score.body.streams if s.name == port.binding.stream
            )
            if not isinstance(stream, AudioStream):
                raise RecsError('audio renderer requires an audio recording port')
            channels = port.binding.channels
            resolved = resolve_input(
                SourceSpec(
                    name='input',
                    record=Path(part.score),
                    selector=RecordSelector(
                        source=stream.source_name or stream.source_id,
                        track=stream.track_name or stream.name,
                        channel=channels[0] if channels else None,
                    ),
                ),
                Path('.'),
                stream.name,
                channels,
                score
                if not score.body.continued_at and not score.body.continued_from
                else None,
            )
            return resolved.model_copy(update={'name': f'{path}/{port_name}'})
        if not isinstance(score, ArrangementScore):
            raise RecsError(f'{path}: audio realization of {score.kind} is unsupported')
        if score.body.connections:
            raise RecsError(
                f'{path}: audio realization of input connections is unsupported'
            )
        if path not in realized:
            addresses = {c.source for c in score.body.clips} | {
                p.binding
                for p in score.outputs
                if isinstance(p.binding, OutputSelection)
            }
            sources = {a: source(part.children[a.name], a.output) for a in addresses}
            graph = validate_graph(score, sources)
            realized[path] = Renderer(score, sources, graph).outputs
        return realized[path][port_name]

    addresses = {c.source for c in edit.body.clips} | {
        p.binding for p in edit.outputs if isinstance(p.binding, OutputSelection)
    }
    return {
        a: source(composition.parts['root'].children[a.name], a.output)
        for a in addresses
    }
