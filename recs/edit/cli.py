import sys
from datetime import datetime
from pathlib import Path
from typing import Annotated

import tyro
from pydantic import BaseModel, ConfigDict, Field
from ufor.codec import score_toml
from ufor.interface import MixBinding, Part, ScoreReference

from recs.base.errors import RecsError
from recs.edit import autocalibrate, calibration_schema, commands, composition, session
from recs.edit.options import EditOptions
from recs.edit.resources import plan_calibration, plan_edit
from recs.edit.schema import CommandKind
from recs.edit.workspace import audio_workspace
from recs.recording import recording_paths


class EditCli(EditOptions, frozen=True):
    scratch_directory: Path | None = None
    inputs: Annotated[list[Path], tyro.conf.Positional] = Field(default_factory=list)

    destination: Annotated[
        Path | None,
        tyro.conf.arg(aliases=('-o',), help='New output session directory'),
    ] = None

    dry_run: bool = False

    model_config = ConfigDict(extra='forbid')


class EditCommandCli(BaseModel, frozen=True):
    """Run a named edit recipe or TOML file. Use COMMAND --help for its options.

    Use compose COMPOSITION.toml to combine recordings into a composition.
    """

    command: Annotated[str, tyro.conf.Positional]
    arguments: Annotated[list[str], tyro.conf.Positional] = Field(default_factory=list)


class CompositionCli(BaseModel, frozen=True):
    scratch_directory: Path | None = None
    record: Annotated[Path | None, tyro.conf.Positional] = None

    destination: Annotated[
        Path | None,
        tyro.conf.arg(aliases=('-o',), help='Composite output directory'),
    ] = None

    dry_run: bool = False

    model_config = ConfigDict(extra='forbid')


class AutocalibrateCli(calibration_schema.AutocalibrateOptions, frozen=True):
    scratch_directory: Path | None = None
    record: Annotated[Path | None, tyro.conf.Positional] = None

    destination: Annotated[
        Path | None,
        tyro.conf.arg(aliases=('-o',), help='New output session directory'),
    ] = None

    dry_run: bool = False

    model_config = ConfigDict(extra='forbid')


class AutocalibrateFileCli(BaseModel, frozen=True):
    scratch_directory: Path | None = None
    destination: Annotated[
        Path | None,
        tyro.conf.arg(aliases=('-o',), help='New output session directory'),
    ] = None

    dry_run: bool = False

    model_config = ConfigDict(extra='forbid')


def main(args: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if args is None else args)
    if not args or args[0] in {'-h', '--help'}:
        tyro.cli(EditCommandCli, args=args, prog='recs edit')
        return 0
    command = args.pop(0)
    cwd = Path.cwd()
    if command == 'compose':
        if args and args[0] in {'-h', '--help'}:
            tyro.cli(
                CompositionCli,
                args=args,
                prog='recs edit compose COMPOSITION.toml',
                description='Combine recordings using a composition TOML file.',
            )
            return 0
        if not args:
            raise RecsError('Expected a composition TOML path')
        composition_path = (cwd / Path(args.pop(0))).resolve()
        return _run_composition(composition_path, args, cwd)
    explicit = (cwd / Path(command)).resolve()
    if composition.is_composition_file(explicit):
        return _run_composition(explicit, args, cwd)
    if autocalibrate.is_autocalibrate_file(explicit):
        return _run_autocalibrate_file(explicit, args, cwd)
    recipe, command_path = commands.resolve_command(command, cwd)
    if commands.command_operation(recipe) == CommandKind.autocalibrate:
        return _run_autocalibrate_command(command, command_path, args, cwd)
    cfg = tyro.cli(EditCli, args=args, prog=f'recs edit {command}')
    input_paths = cfg.inputs
    definitions = {} if cfg.dry_run else None
    edit_directory = command_path.parent if recipe.get('kind') == 'arrangement' else cwd
    try:
        complete = commands.complete_or_generate(
            recipe,
            input_paths,
            cfg,
            definitions,
        )
    except commands.SessionRecordRequired:
        input_paths = [commands.latest_record(cwd)]
        complete = commands.complete_or_generate(
            recipe,
            input_paths,
            cfg,
            definitions,
        )
    destination = cfg.destination or recording_paths.available_directory(
        cwd / f'{datetime.now():%Y-%m-%d %H-%M-%S} edit'
    )
    if cfg.dry_run:
        with audio_workspace(cfg.scratch_directory):
            plan = plan_edit(complete, edit_directory, destination, definitions)
            print('\n'.join(f'# {s}' for s in plan.summary().splitlines()))
            print(
                score_toml(
                    session.canonical_edit(complete, {}, destination, edit_directory)
                ),
                end='',
            )
        return 0
    print(f'Command: {command} ({command_path})')
    print(
        'Inputs: ' + (', '.join(str(p) for p in input_paths) or 'declared by edit TOML')
    )
    print(f'Media types: {", ".join(complete.body.media_types)}')
    print(f'Sample rate: {complete.timebases[0].rate.numerator}')
    source_names = [_part_source_name(part) for part in complete.body.parts]
    print(f'Channels: {", ".join(source_names)}')
    print(f'Tracks: {", ".join(t.name for t in complete.body.tracks)}')
    print(f'Buses: {", ".join(b.name for b in complete.body.buses) or "none"}')
    print(f'Output session: {destination}')
    for output in complete.outputs:
        if not isinstance(output.binding, MixBinding):
            print(f'Output: {output.name}')
            continue
        start = output.binding.start or 0
        end = (
            output.binding.end if output.binding.end is not None else 'arrangement end'
        )
        target = next(d for d in complete.destinations if d.output == output.name)
        print(f'Output: {target.path} ({target.format}, frames {start}:{end})')
    with audio_workspace(cfg.scratch_directory):
        session.execute_edit(complete, edit_directory, destination)
    return 0


def _part_source_name(part: Part) -> str:
    if isinstance(part.score, ScoreReference):
        return part.score.path or '<unresolved score>'
    return f'<inline {part.score.name}>'


def _run_autocalibrate_command(
    command: str, command_path: Path, args: list[str], cwd: Path
) -> int:
    cfg = tyro.cli(AutocalibrateCli, args=args, prog=f'recs edit {command}')
    record_path = cfg.record or commands.latest_record(cwd)
    value = autocalibrate.autocalibrate_from_options(record_path, cfg)
    destination = cfg.destination or recording_paths.available_directory(
        cwd / f'{datetime.now():%Y-%m-%d %H-%M-%S} edit'
    )
    if cfg.dry_run:
        with audio_workspace(cfg.scratch_directory):
            print(
                plan_calibration(record_path, value.channels, destination).summary(),
                end='',
            )
        return 0
    with audio_workspace(cfg.scratch_directory):
        autocalibrate.execute_autocalibrate(value, command_path.parent, destination)
    return 0


def _run_autocalibrate_file(path: Path, args: list[str], cwd: Path) -> int:
    cfg = tyro.cli(AutocalibrateFileCli, args=args, prog=f'recs edit {path}')
    value = autocalibrate.parse_autocalibrate(path.read_text())
    destination = cfg.destination or recording_paths.available_directory(
        cwd / f'{datetime.now():%Y-%m-%d %H-%M-%S} edit'
    )
    if cfg.dry_run:
        if value.record is None:
            raise RecsError('Calibration planning requires a recording input')
        with audio_workspace(cfg.scratch_directory):
            print(
                plan_calibration(
                    path.parent / value.record, value.channels, destination
                ).summary(),
                end='',
            )
        return 0
    with audio_workspace(cfg.scratch_directory):
        autocalibrate.execute_autocalibrate(value, path.parent, destination)
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
        with audio_workspace(cfg.scratch_directory):
            print(
                composition.composition_summary(value, path, record_path, destination),
                end='',
            )
        return 0
    with audio_workspace(cfg.scratch_directory):
        result = composition.execute_composition(value, path, record_path, destination)
    print(f'Result: {result}')
    return 0
