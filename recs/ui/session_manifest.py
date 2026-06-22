import json
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel, Field


class ManifestFile(BaseModel):
    path: str
    track: int
    channels: int
    sample_rate: int
    bit_depth: int
    source: str | None = None


class ManifestEvent(BaseModel):
    timestamp: str
    type: str
    source: str | None = None
    track: str | None = None
    key: str | None = None


class SessionManifest(BaseModel):
    started_at: str
    ended_at: str
    duration: float
    events: list[ManifestEvent] = Field(default_factory=list)
    files: list[ManifestFile] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    def write(self, path: Path) -> Path:
        target = _available_path(path)
        target.parent.mkdir(exist_ok=True, parents=True)
        target.write_text(
            json.dumps(self.model_dump(mode='json', exclude_none=True), indent=2)
            + '\n'
        )
        return target


def timestamp_to_json(timestamp: float) -> str:
    return (
        datetime.fromtimestamp(timestamp, timezone.utc)
        .isoformat(timespec='milliseconds')
        .replace('+00:00', 'Z')
    )


def _available_path(path: Path) -> Path:
    if not path.exists():
        return path

    index = 1
    while True:
        candidate = path.with_stem(f'{path.stem}-{index}')
        if not candidate.exists():
            return candidate
        index += 1
