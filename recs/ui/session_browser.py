import json
from pathlib import Path

from pydantic import BaseModel, Field

from . import session_manifest

MANIFEST_NAME = 'recs-session.jsonl'


class SessionSummary(BaseModel):
    path: str
    started_at: str
    ended_at: str | None
    duration: float | None
    files: int
    warnings: list[str] = Field(default_factory=list)
    key_markers: int = 0


def main(argv: list[str]) -> int:
    root = Path(argv[0]) if argv else Path()
    summaries = list(scan(root))
    print(json.dumps([s.model_dump(mode='json') for s in summaries], indent=2))
    return 0


def scan(root: Path) -> list[SessionSummary]:
    if root.name == MANIFEST_NAME:
        manifests = [root]
    else:
        manifests = sorted(root.glob(f'**/{MANIFEST_NAME}'))
    return [summary for path in manifests if (summary := _summary(path))]


def _summary(path: Path) -> SessionSummary | None:
    try:
        manifest = session_manifest.read(path)
    except OSError:
        return None
    if not manifest.started_at:
        return None
    return SessionSummary(
        path=path.as_posix(),
        started_at=manifest.started_at,
        ended_at=manifest.ended_at,
        duration=manifest.duration,
        files=sum(1 for f in manifest.files if f.type == 'file_finished'),
        warnings=manifest.warnings + manifest.errors,
        key_markers=sum(1 for e in manifest.events if e.key),
    )
