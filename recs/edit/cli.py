import sys
from datetime import datetime
from pathlib import Path
from typing import Annotated

import tyro
from pydantic import BaseModel, ConfigDict, Field

from recs.base.errors import RecsError
from recs.edit import commands, composition, session
from recs.edit.options import EditOptions
from recs.edit.schema import canonical_toml
from recs.ui import recording_paths


class EditCli(EditOptions, frozen=True):
    inputs: Annotated[list[Path], tyro.conf.Positional] = Field(default_factory=list)

    destination: Annotated[
        Path | None,
        tyro.conf.arg(aliases=('-o',), help='New output session directory'),
    ] = None

    dry_run: bool = False

    model_config = ConfigDict(extra='forbid')


class CompositionCli(BaseModel, frozen=True):
    record: Annotated[Path | None, tyro.conf.Positional] = None

    destination: Annotated[
        Path | None,
        tyro.conf.arg(aliases=('-o',), help='Composite output directory'),
    ] = None

    dry_run: bool = False

    model_config = ConfigDict(extra='forbid')


def main(args: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if args is None else args)
    if not args:
        raise RecsError('Expected an edit command name or TOML path')
    command = args.pop(0)
    cwd = Path.cwd()
    if command == 'compose':
        if not args:
            raise RecsError('Expected a composition TOML path')
        composition_path = (cwd / Path(args.pop(0))).resolve()
        return _run_composition(composition_path, args, cwd)
    explicit = (cwd / Path(command)).resolve()
    if composition.is_composition_file(explicit):
        return _run_composition(explicit, args, cwd)
    recipe, command_path = commands.resolve_command(command, cwd)
    cfg = tyro.cli(EditCli, args=args, prog=f'recs edit {command}')
    input_paths = cfg.inputs
    try:
        complete = commands.complete_or_generate(
            recipe,
            input_paths,
            cfg,
        )
    except commands.SessionRecordRequired:
        input_paths = [commands.latest_record(cwd)]
        complete = commands.complete_or_generate(
            recipe,
            input_paths,
            cfg,
        )
    destination = cfg.destination or recording_paths.available_directory(
        cwd / f'{datetime.now():%Y-%m-%d %H-%M-%S} edit'
    )
    if cfg.dry_run:
        prepared = session.prepare_edit(complete, command_path.parent, destination)
        print(canonical_toml(prepared.edit), end='')
        return 0
    print(f'Command: {command} ({command_path})')
    print(
        'Inputs: ' + (', '.join(str(p) for p in input_paths) or 'declared by edit TOML')
    )
    print(f'Media types: {", ".join(complete.media_types)}')
    print(f'Sample rate: {complete.sample_rate}')
    source_names = [
        str(s.channel or f'{s.file}:{"-".join(str(c) for c in s.channels)}')
        for s in complete.sources
    ]
    print(f'Channels: {", ".join(source_names)}')
    print(f'Tracks: {", ".join(t.id for t in complete.tracks)}')
    print(f'Buses: {", ".join(b.id for b in complete.buses) or "none"}')
    print(f'Output session: {destination}')
    for output in complete.outputs:
        start = output.start or 0
        end = output.end if output.end is not None else 'arrangement end'
        print(f'Output: {output.path} ({output.format}, frames {start}:{end})')
    session.execute_edit(complete, command_path.parent, destination)
    return 0


def _run_composition(path: Path, args: list[str], cwd: Path) -> int:
    if not path.is_file():
        raise RecsError(f'Composition file does not exist: {path}')
    value = composition.parse_composition(path.read_text())
    cfg = tyro.cli(CompositionCli, args=args, prog=f'recs edit {path}')
    record_path = cfg.record or commands.latest_record(cwd)
    destination = cfg.destination
    if value.edits and destination is None:
        destination = recording_paths.available_directory(
            cwd / f'{datetime.now():%Y-%m-%d %H-%M-%S} edit'
        )
    if cfg.dry_run:
        print(
            composition.composition_summary(value, path, record_path, destination),
            end='',
        )
        return 0
    result = composition.execute_composition(value, path, record_path, destination)
    print(f'Result: {result}')
    return 0
