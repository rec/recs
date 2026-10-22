"""Read common recording documents and their explicit volume continuations."""

from pathlib import Path

from pydantic import ValidationError
from tomlkit.exceptions import ParseError
from ufor.codec import parse_score
from ufor.recording import RecordingScore

from ..base.errors import RecsError


def read_recording(path: Path) -> RecordingScore:
    path = recording_path(path)
    try:
        if path.name == 'session-record.jsonl':
            from .finalize import prepare_recording

            document, _ = prepare_recording(path, verify_files=False)
            return document
        document = parse_score(path.read_text())
    except (OSError, ValidationError, ParseError) as error:
        raise RecsError(f'Cannot read recording {path}: {error}') from error
    if not isinstance(document, RecordingScore):
        raise RecsError(f'Expected a recording document: {path}')
    return document


def recording_path(path: Path) -> Path:
    """Select a session's saved index or its capture journal."""
    candidate = path / 'recording.toml' if path.is_dir() else path
    if candidate.name == 'recording.toml' and not candidate.is_file():
        journal = candidate.with_name('session-record.jsonl')
        if journal.is_file():
            return journal
    return candidate if candidate.is_file() else path


def find_recordings(root: Path) -> list[Path]:
    selected = recording_path(root)
    if not root.is_dir() and selected.is_file():
        return [selected]
    directories = {
        p.parent
        for n in ('recording.toml', 'session-record.jsonl')
        for p in root.rglob(n)
    }
    return sorted(recording_path(p) for p in directories)


def read_recording_chain(path: Path) -> list[tuple[Path, RecordingScore]]:
    pending = [recording_path(path).resolve()]
    result: list[tuple[Path, RecordingScore]] = []
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
        pending.extend(recording_path(current.parent / p).resolve() for p in links)
    return result
