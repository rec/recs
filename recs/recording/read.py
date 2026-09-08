"""Read common recording documents and their explicit volume continuations."""

from pathlib import Path

from pydantic import ValidationError
from tomlkit.exceptions import ParseError
from ufor.codec import parse_document
from ufor.recording import RecordingDocument

from ..base.errors import RecsError


def read_recording(path: Path) -> RecordingDocument:
    try:
        document = parse_document(path.read_text())
    except (OSError, ValidationError, ParseError) as error:
        raise RecsError(f'Cannot read recording {path}: {error}') from error
    if not isinstance(document, RecordingDocument):
        raise RecsError(f'Expected a recording document: {path}')
    return document


def read_recording_chain(path: Path) -> list[tuple[Path, RecordingDocument]]:
    pending = [path.resolve()]
    result: list[tuple[Path, RecordingDocument]] = []
    seen: set[Path] = set()
    while pending:
        current = pending.pop(0)
        if current in seen:
            continue
        seen.add(current)
        document = read_recording(current)
        result.append((current, document))
        links = document.body.continued_at + (
            [document.body.continued_from] if document.body.continued_from else []
        )
        pending.extend((current.parent / p).resolve() for p in links)
    return result
