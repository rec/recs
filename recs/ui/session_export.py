import os
import shutil
import uuid
from pathlib import Path
from typing import Annotated

import tomlkit
import tyro
from pydantic import BaseModel
from ufor.codec import document_toml

from ..base.errors import RecsError
from ..misc.legal_filename import legal_filename
from ..recording.files import sealed_asset
from ..recording.read import read_recording_chain


class ExportCli(BaseModel, frozen=True):
    record: Annotated[Path, tyro.conf.Positional]
    destination: Annotated[Path, tyro.conf.Positional]


def export(record: Path, destination: Path) -> Path:
    record = record.resolve()
    destination = destination.resolve()
    if destination.exists():
        raise RecsError(f'Export destination already exists: {destination}')
    records = read_recording_chain(record)
    temporary = destination.with_name(
        f'.{destination.name}.recs-export-{uuid.uuid4().hex}'
    )
    targets = {
        p: temporary
        / (
            'recording.toml'
            if i == 0
            else f'sessions/{i:03d}-{legal_filename(p.parent.name)}/recording.toml'
        )
        for i, (p, _) in enumerate(records)
    }
    for path, document in records:
        if document.body.state != 'sealed':
            raise RecsError(f'Cannot export an unfinished recording: {path}')
        for asset in document.assets:
            actual = sealed_asset(
                path.parent / asset.path, path.parent, asset.id, asset.encoding
            )
            if actual.sha256 != asset.sha256 or actual.byte_length != asset.byte_length:
                raise RecsError(f'Asset bytes disagree with recording: {asset.path}')
    temporary.mkdir(parents=True)
    file_count = total_bytes = 0
    try:
        for path, document in records:
            output = targets[path]
            output.parent.mkdir(parents=True, exist_ok=True)
            for asset in document.assets:
                source = path.parent / asset.path
                target = output.parent / asset.path
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
                actual = sealed_asset(target, output.parent, asset.id, asset.encoding)
                if (
                    actual.sha256 != asset.sha256
                    or actual.byte_length != asset.byte_length
                ):
                    raise RecsError(f'Exported asset differs: {asset.path}')
                file_count += 1
                total_bytes += asset.byte_length
            body = document.body
            links = body.continued_at + (
                [body.continued_from] if body.continued_from else []
            )
            rewritten = {
                p: Path(
                    os.path.relpath(targets[(path.parent / p).resolve()], output.parent)
                ).as_posix()
                for p in links
            }
            exported = document.model_copy(
                update={
                    'body': body.model_copy(
                        update={
                            'continued_from': rewritten[body.continued_from]
                            if body.continued_from
                            else None,
                            'continued_at': [rewritten[p] for p in body.continued_at],
                        }
                    )
                }
            )
            output.write_text(document_toml(exported))
        (temporary / 'export-summary.toml').write_text(
            tomlkit.dumps(
                {
                    'version': 1,
                    'source_record': str(record),
                    'record_count': len(records),
                    'file_count': file_count,
                    'total_bytes': total_bytes,
                    'records': [
                        {
                            'source': str(p),
                            'path': targets[p].relative_to(temporary).as_posix(),
                        }
                        for p, _ in records
                    ],
                }
            )
        )
        temporary.replace(destination)
    except (OSError, RecsError):
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return destination


def main(argv: list[str] | None = None) -> int:
    command = tyro.cli(
        ExportCli,
        args=argv,
        prog='recs session export',
        description='Copy a recording and its continuations into a portable directory.',
    )
    print(export(command.record, command.destination))
    return 0
