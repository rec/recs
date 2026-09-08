"""Convert historical v3 journals while preserving media and original evidence."""

import hashlib
from pathlib import Path
from typing import Annotated

import tyro
from pydantic import BaseModel
from ufor.codec import document_toml, parse_document

from ..base.errors import RecsError
from .files import Verification, verify_recording
from .legacy_finalize import prepare_legacy_recording


class MigrateSession(BaseModel, frozen=True):
    session: Annotated[Path, tyro.conf.Positional]
    paths_relative_to: Path | None = None


def main(argv: list[str] | None = None) -> int:
    config = tyro.cli(MigrateSession, args=argv, prog='recs session migrate')
    path, verification = migrate_session(config.session, config.paths_relative_to)
    print(path)
    print(
        f'Verified {verification.asset_count} assets, '
        f'{verification.audio_frames} audio frames, {verification.event_count} events.'
    )
    for note in verification.notes:
        print(note)
    return 0


def migrate_session(
    session: Path, paths_relative_to: Path | None = None
) -> tuple[Path, Verification]:
    root = session.resolve()
    journal = root / 'session-record.jsonl'
    output = root / 'recording.toml'
    snapshot = root / 'migration/session-record-v3.jsonl'
    report_path = root / 'migration/report.json'
    if not snapshot.parent.resolve().is_relative_to(root):
        raise RecsError('Migration directory escapes the session directory')
    for path in (output, snapshot, report_path):
        if path.exists():
            raise RecsError(f'Migration output already exists: {path}')
    document, notes = prepare_legacy_recording(journal, paths_relative_to)
    # No writes occur until every referenced finished payload has been verified.
    verification = verify_recording(document, root)
    original = journal.read_bytes()
    journal_asset = next(a for a in document.assets if a.id == document.body.journal)
    if hashlib.sha256(original).hexdigest() != journal_asset.sha256:
        raise RecsError(
            'Session record changed during migration; retry after capture stops'
        )
    snapshot.parent.mkdir(exist_ok=True)
    with snapshot.open('xb') as target:
        target.write(original)
    document = document.model_copy(
        update={
            'assets': [
                a.model_copy(update={'path': snapshot.relative_to(root).as_posix()})
                if a.id == document.body.journal
                else a
                for a in document.assets
            ]
        }
    )
    with output.open('x') as target:
        target.write(document_toml(document))
    restored = parse_document(output.read_text())
    if (
        restored != document
        or journal.read_bytes() != original
        or snapshot.read_bytes() != original
    ):
        raise RecsError('Written migration differs from the verified source')
    verification = verification.model_copy(update={'notes': notes})
    with report_path.open('x') as target:
        target.write(verification.model_dump_json(indent=2) + '\n')
    return output, verification
