import os
import shutil
import tempfile
from pathlib import Path
from typing import Annotated

import tomlkit
import tyro
from pydantic import BaseModel, Field
from ufor.codec import score_toml

from ..base.errors import RecsError
from ..misc.legal_filename import legal_filename
from .files import sealed_asset
from .read import read_recording_chain
from .recording_paths import write_text_atomically


class ExportCli(BaseModel, frozen=True):
    record: Annotated[Path, tyro.conf.Positional]
    destination: Annotated[Path, tyro.conf.Positional]
    resume: Path | None = None
    """Resume the reported staging directory after an interrupted export."""


class ExportProgress(BaseModel, frozen=True):
    source_records: dict[str, str]
    destination: Path
    copied: list[str] = Field(default_factory=list)
    verified: list[str] = Field(default_factory=list)
    remaining: list[str] = Field(default_factory=list)
    failed: list[str] = Field(default_factory=list)


def export(record: Path, destination: Path, resume: Path | None = None) -> Path:
    record = record.resolve()
    destination = destination.absolute()
    if destination.exists() or destination.is_symlink():
        raise RecsError(f'Export destination already exists: {destination}')
    destination = destination.resolve()
    records = read_recording_chain(record)
    fingerprints = {
        str(p): sealed_asset(p, p.parent, 'document', 'toml').sha256 for p, _ in records
    }
    targets = {
        p: Path(
            'recording.toml'
            if i == 0
            else f'sessions/{i:03d}-{legal_filename(p.parent.name)}/recording.toml'
        )
        for i, (p, _) in enumerate(records)
    }
    assets = {
        (targets[p].parent / a.path).as_posix(): (p.parent, a)
        for p, d in records
        for a in d.assets
    }
    reserved = {p.as_posix() for p in targets.values()} | {
        'export-progress.json',
        '.export-progress.json.tmp',
        'export-summary.toml',
    }
    paths = {Path(p) for p in [*assets, *reserved]}
    if (
        len(assets) != sum(len(d.assets) for _, d in records)
        or assets.keys() & reserved
        or any(p in paths for q in paths for p in q.parents)
    ):
        raise RecsError('Export paths conflict with another asset or export metadata')
    for path, document in records:
        if document.body.state != 'sealed':
            raise RecsError(f'Cannot export an unfinished recording: {path}')
        for asset in document.assets:
            actual = sealed_asset(
                path.parent / asset.path, path.parent, asset.name, asset.encoding
            )
            if actual.sha256 != asset.sha256 or actual.byte_length != asset.byte_length:
                raise RecsError(f'Asset bytes disagree with recording: {asset.path}')
    if resume is not None:
        temporary = resume.resolve()
        try:
            progress = ExportProgress.model_validate_json(
                (temporary / 'export-progress.json').read_text()
            )
        except (OSError, ValueError) as error:
            raise RecsError(
                f'Cannot read export staging progress at {temporary}: {error}'
            ) from error
        if (
            progress.source_records != fingerprints
            or progress.destination != destination
        ):
            raise RecsError(
                'Staging directory belongs to different source documents or destination'
            )
        completed = set(progress.copied + progress.verified)
        if not completed <= assets.keys():
            raise RecsError('Staging progress contains unknown assets')
    else:
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = Path(
            tempfile.mkdtemp(
                prefix=f'.{destination.name}.recs-export-', dir=destination.parent
            )
        )
        completed = set()
    for relative in paths:
        target = temporary / relative
        if any(p.is_symlink() for p in [target, *target.parents] if p != temporary):
            raise RecsError(f'Unsafe staged export path: {target}')
    progress = ExportProgress(
        source_records=fingerprints,
        destination=destination,
        remaining=sorted(assets),
    )
    file_count = total_bytes = 0
    current = ''
    try:
        # Revalidate every completed file before changing any persisted progress.
        for relative in sorted(completed):
            current = relative
            _, asset = assets[relative]
            target = temporary / relative
            actual = sealed_asset(target, temporary, asset.name, asset.encoding)
            if actual.sha256 != asset.sha256 or actual.byte_length != asset.byte_length:
                raise RecsError(f'Completed staged asset differs: {relative}')
            progress.verified.append(relative)
            progress.remaining.remove(relative)
        write_text_atomically(
            temporary / 'export-progress.json', progress.model_dump_json(indent=2)
        )
        for path, document in records:
            output = temporary / targets[path]
            output.parent.mkdir(parents=True, exist_ok=True)
            for asset in document.assets:
                current = (targets[path].parent / asset.path).as_posix()
                source = path.parent / asset.path
                target = output.parent / asset.path
                target.parent.mkdir(parents=True, exist_ok=True)
                if current not in completed:
                    shutil.copy2(source, target)
                actual = sealed_asset(target, output.parent, asset.name, asset.encoding)
                if (
                    actual.sha256 != asset.sha256
                    or actual.byte_length != asset.byte_length
                ):
                    raise RecsError(f'Exported asset differs: {asset.path}')
                if current not in completed:
                    progress.copied.append(current)
                    progress.remaining.remove(current)
                    write_text_atomically(
                        temporary / 'export-progress.json',
                        progress.model_dump_json(indent=2),
                    )
                file_count += 1
                total_bytes += asset.byte_length
            body = document.body
            links = body.continued_at + (
                [body.continued_from] if body.continued_from else []
            )
            rewritten = {
                p: Path(
                    os.path.relpath(
                        temporary / targets[(path.parent / p).resolve()], output.parent
                    )
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
            output.write_text(score_toml(exported))
        for relative, (_, asset) in assets.items():
            current = relative
            actual = sealed_asset(
                temporary / relative, temporary, asset.name, asset.encoding
            )
            if actual.sha256 != asset.sha256 or actual.byte_length != asset.byte_length:
                raise RecsError(f'Exported asset differs: {relative}')
        current = ''
        for path, _ in records:
            if (
                sealed_asset(path, path.parent, 'document', 'toml').sha256
                != fingerprints[str(path)]
            ):
                raise RecsError(f'Source document changed during export: {path}')
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
                            'path': targets[p].as_posix(),
                        }
                        for p, _ in records
                    ],
                }
            )
        )
        if destination.exists() or destination.is_symlink():
            raise RecsError(
                f'Export destination appeared during copying: {destination}'
            )
        temporary.rename(destination)
    except (OSError, RecsError, KeyboardInterrupt) as error:
        if current:
            progress.failed.append(current)
        # A disconnected/full disk can also prevent updating the progress report.
        # The previous atomic report remains usable for explicit resume.
        if not completed or len(progress.verified) == len(completed):
            try:
                write_text_atomically(
                    temporary / 'export-progress.json',
                    progress.model_dump_json(indent=2),
                )
            except OSError:
                pass
        raise RecsError(
            f'Export not published; staging retained at {temporary}. '
            f'Copied {len(progress.copied)}, verified {len(progress.verified)}, '
            f'remaining {len(progress.remaining)}, '
            f'failed {current or "publication"}: {error}'
        ) from error
    return destination


def main(argv: list[str] | None = None) -> int:
    command = tyro.cli(
        ExportCli,
        args=argv,
        prog='recs session export',
        description='Copy a recording and its continuations into a portable directory.',
    )
    result = export(command.record, command.destination, command.resume)
    progress = ExportProgress.model_validate_json(
        (result / 'export-progress.json').read_text()
    )
    print(result)
    print(
        f'Copied {len(progress.copied)}, verified {len(progress.verified)}, '
        f'remaining {len(progress.remaining)}, failed {len(progress.failed)}'
    )
    return 0
