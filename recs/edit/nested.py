"""Host loading and realization of portable recording and arrangement graphs."""

from hashlib import sha256
from pathlib import Path

from ufor.arrangement import ArrangementDocument
from ufor.codec import document_toml, parse_document
from ufor.composition import Composition, DefinitionRecord
from ufor.interface import (
    Address,
    Direction,
    StreamBinding,
)
from ufor.recording import AudioStream, RecordingDocument
from ufor.references import RecordSelector

from recs.base.errors import RecsError
from recs.edit.inputs import SourceSpec
from recs.edit.materialized import MaterializedAudio
from recs.edit.record import ResolvedSource, resolve_input


def load_composition(
    edit: ArrangementDocument,
    directory: Path,
    package_root: Path | None = None,
    supplied: dict[Path, RecordingDocument] | None = None,
) -> Composition:
    root = directory.resolve()
    records: dict[str, DefinitionRecord] = {}
    active: set[Path] = set()

    def load(path: Path) -> str:
        path = path.resolve()
        if package_root is not None and not path.is_relative_to(package_root.resolve()):
            raise RecsError(f'Definition escapes package root: {path}')
        identity = str(path)
        if path in active:
            raise RecsError(f'Definition cycle: {path}')
        if identity in records:
            return identity
        active.add(path)
        if supplied is not None and path in supplied:
            document = supplied[path]
            data = document_toml(document).encode()
        else:
            data = path.read_bytes()
            document = parse_document(data.decode())
        links = {}
        if isinstance(document, ArrangementDocument):
            links = {
                n.definition.path: load(path.parent / n.definition.path)
                for n in document.body.nodes
            }
        records[identity] = DefinitionRecord(
            document=document, references=links, sha256=sha256(data).hexdigest()
        )
        active.remove(path)
        return identity

    links = {n.definition.path: load(root / n.definition.path) for n in edit.body.nodes}
    records['root'] = DefinitionRecord(document=edit, references=links)
    return Composition('root', records)


def resolve_sources(
    edit: ArrangementDocument,
    edit_directory: Path,
    supplied: dict[Path, RecordingDocument] | None = None,
) -> dict[Address, ResolvedSource | MaterializedAudio]:
    from recs.edit.graph import validate_graph
    from recs.edit.render import Renderer

    composition = load_composition(edit, edit_directory, supplied=supplied)
    if any(p.direction == Direction.input for p in edit.ports):
        raise RecsError('offline audio rendering requires supplied root inputs')
    realized: dict[str, dict[str, MaterializedAudio]] = {}

    def source(path: str, port_name: str) -> ResolvedSource | MaterializedAudio:
        instance = composition.instances[path]
        document = composition.definitions[instance.definition].document
        port = composition.port(path, port_name)
        if isinstance(port.binding, Address):
            return source(instance.children[port.binding.node], port.binding.port)
        if isinstance(document, RecordingDocument) and isinstance(
            port.binding, StreamBinding
        ):
            stream = next(
                s for s in document.body.streams if s.id == port.binding.stream
            )
            if not isinstance(stream, AudioStream):
                raise RecsError('audio renderer requires an audio recording port')
            channels = port.binding.channels
            resolved = resolve_input(
                SourceSpec(
                    id='input',
                    record=Path(instance.definition),
                    selector=RecordSelector(
                        source=stream.source_name or stream.source_id,
                        track=stream.track_name or stream.id,
                        channel=channels[0] if channels else None,
                    ),
                ),
                Path('.'),
                stream.id,
                channels,
                document
                if not document.body.continued_at and not document.body.continued_from
                else None,
            )
            return resolved.model_copy(update={'id': f'{path}/{port_name}'})
        if not isinstance(document, ArrangementDocument):
            raise RecsError(
                f'{path}: audio realization of {document.kind} is unsupported'
            )
        if document.body.connections:
            raise RecsError(
                f'{path}: audio realization of input connections is unsupported'
            )
        if path not in realized:
            addresses = {c.source for c in document.body.clips} | {
                p.binding
                for p in document.ports
                if isinstance(p.binding, Address) and p.direction == Direction.output
            }
            sources = {a: source(instance.children[a.node], a.port) for a in addresses}
            graph = validate_graph(document, sources)
            realized[path] = Renderer(document, sources, graph).outputs
        return realized[path][port_name]

    addresses = {c.source for c in edit.body.clips} | {
        p.binding
        for p in edit.ports
        if isinstance(p.binding, Address) and p.direction == Direction.output
    }
    return {
        a: source(composition.instances['root'].children[a.node], a.port)
        for a in addresses
    }
