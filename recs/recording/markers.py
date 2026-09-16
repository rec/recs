"""Read marker evidence without inferring source positions from wall time."""

from pathlib import Path
from typing import Annotated

import tyro
from pydantic import BaseModel, Field
from ufor.recording import RecordingScore

from ..base.errors import RecsError
from . import legacy, session_record
from .files import sealed_asset
from .read import read_recording


class Marker(BaseModel, frozen=True):
    number: int
    label: str
    timestamp: str
    positions: list[session_record.MarkerPosition] = Field(default_factory=list)


class MarkersCli(BaseModel, frozen=True):
    """List numbered markers and their available source-frame evidence."""

    path: Annotated[Path, tyro.conf.Positional]
    json_output: Annotated[bool, tyro.conf.arg(name='json')] = False


def read_markers(path: Path, document: RecordingScore) -> list[Marker]:
    if document.body.journal is None:
        return []
    asset = next(a for a in document.assets if a.name == document.body.journal)
    journal_path = path.parent / asset.path
    actual = sealed_asset(journal_path, path.parent, asset.name, asset.encoding)
    if actual.sha256 != asset.sha256 or actual.byte_length != asset.byte_length:
        raise RecsError('Marker journal bytes disagree with the recording document')
    historical = asset.encoding == 'recs-session-v3'
    journal = (
        legacy.read(journal_path) if historical else session_record.read(journal_path)
    )
    if journal.errors:
        raise RecsError('; '.join(journal.errors))
    return [
        Marker(
            number=i + 1,
            label=e.label or e.key or '',
            timestamp=e.timestamp,
            positions=(e.positions or [])
            if isinstance(e, session_record.EventRecord)
            else [],
        )
        for i, e in enumerate(
            e for e in journal.events if e.type in {'mark', 'key_pressed'}
        )
    ]


def main(argv: list[str]) -> int:
    command = tyro.cli(MarkersCli, args=argv, prog='recs session markers')
    path = command.path / 'recording.toml' if command.path.is_dir() else command.path
    markers = read_markers(path, read_recording(path))
    if command.json_output:
        import json

        print(json.dumps([m.model_dump(mode='json') for m in markers], indent=2))
    else:
        for marker in markers:
            print(f'{marker.number}: {marker.label!r} ({marker.timestamp})')
            for position in marker.positions:
                print(
                    f'  {position.source}: {position.clock_id}, '
                    f'frame {position.frame}, {position.sample_rate} Hz; '
                    f'{position.timing_source}, observed {position.observed_at}'
                )
            if not marker.positions:
                print('  Unpositioned: no source-frame evidence')
    return 0
