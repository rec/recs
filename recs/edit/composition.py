import os
from pathlib import Path
from typing import Literal

import tomlkit
from pydantic import BaseModel, ConfigDict, Field, field_validator

from recs.base.errors import RecsError
from recs.edit import commands, session
from recs.edit.options import EditOptions
from recs.edit.schema import parse_edit, parse_partial_edit
from recs.misc import legal_filename
from recs.ui import session_record


class CompositionStep(EditOptions, frozen=True):
    command: str

    @field_validator('command')
    @classmethod
    def validate_command(cls, value: str) -> str:
        if not value.strip():
            raise ValueError('command must not be empty')
        return value


class CompositionEdit(BaseModel, frozen=True):
    schema_version: Literal[1]
    kind: Literal['composition']
    edits: list[CompositionStep] = Field(default_factory=list)

    model_config = ConfigDict(extra='forbid')


class ResolvedStep(BaseModel, frozen=True):
    step: CompositionStep
    command_path: Path
    recipe: dict[str, object]
    directory_name: str
    recipe_name: str

    model_config = ConfigDict(extra='forbid')


def parse_composition(text: str) -> CompositionEdit:
    return CompositionEdit.model_validate(tomlkit.parse(text))


def canonical_composition(value: CompositionEdit) -> str:
    return tomlkit.dumps(value.model_dump(mode='json', exclude_none=True))


def is_composition_file(path: Path) -> bool:
    if not path.is_file():
        return False
    return tomlkit.parse(path.read_text()).get('kind') == 'composition'


def resolve_composition(value: CompositionEdit, directory: Path) -> list[ResolvedStep]:
    result: list[ResolvedStep] = []
    for index, step in enumerate(value.edits, 1):
        recipe, command_path = commands.resolve_command(step.command, directory)
        text = tomlkit.dumps(recipe)
        try:
            parse_edit(text)
        except ValueError:
            partial = parse_partial_edit(text)
            if partial.command is None or partial.command.operation is None:
                raise RecsError(
                    f'Composite child {index} has no _command.operation: {step.command}'
                ) from None
        else:
            raise RecsError(
                f'Composite child {index} is a complete arrangement and does not '
                f'consume its input session: {step.command}'
            )
        name = legal_filename.legal_filename(Path(step.command).stem) or 'edit'
        result.append(
            ResolvedStep(
                step=step,
                command_path=command_path,
                recipe={k: v for k, v in recipe.items() if k != 'extends'},
                directory_name=f'{index:03d}-{name}',
                recipe_name=f'{index:03d}-{name}.toml',
            )
        )
    return result


def execute_composition(
    value: CompositionEdit,
    composition_path: Path,
    record_path: Path,
    destination: Path | None,
) -> Path:
    record_path = _validate_record(record_path)
    resolved = resolve_composition(value, composition_path.parent)
    if not resolved:
        if destination is not None:
            raise RecsError('An empty composition does not create a destination')
        return record_path
    if destination is None:
        raise RecsError('A non-empty composition requires a destination')
    if destination.exists():
        raise RecsError(f'Output composition directory already exists: {destination}')

    destination.mkdir(parents=True)
    commands_directory = destination / 'commands'
    commands_directory.mkdir()
    canonical_steps: list[CompositionStep] = []
    for resolved_step in resolved:
        recipe_path = commands_directory / resolved_step.recipe_name
        recipe_path.write_text(tomlkit.dumps(resolved_step.recipe))
        canonical_steps.append(
            resolved_step.step.model_copy(
                update={'command': _relative_path(recipe_path, destination).as_posix()}
            )
        )
    canonical = value.model_copy(update={'edits': canonical_steps})
    (destination / 'edit.toml').write_text(canonical_composition(canonical))

    current_record = record_path
    for resolved_step in resolved:
        complete = commands.complete_or_generate(
            resolved_step.recipe, [current_record], resolved_step.step
        )
        current_record = session.execute_edit(
            complete,
            resolved_step.command_path.parent,
            destination / resolved_step.directory_name,
        )
    return current_record


def composition_summary(
    value: CompositionEdit,
    composition_path: Path,
    record_path: Path,
    destination: Path | None,
) -> str:
    record_path = _validate_record(record_path)
    resolved = resolve_composition(value, composition_path.parent)
    if not resolved:
        if destination is not None:
            raise RecsError('An empty composition does not create a destination')
        return f'Record: {record_path}\nEdits: none\nResult: {record_path}\n'
    if destination is None:
        raise RecsError('A non-empty composition requires a destination')
    if destination.exists():
        raise RecsError(f'Output composition directory already exists: {destination}')

    lines = [f'Record: {record_path}', f'Output composition: {destination}']
    for index, resolved_step in enumerate(resolved, 1):
        options = resolved_step.step
        selectors = ', '.join(options.channel) or 'all compatible tracks'
        format_name = str(options.format or 'default')
        subtype = str(options.subtype or 'default')
        lines.append(
            f'{index}: {resolved_step.step.command} ({resolved_step.command_path})'
        )
        lines.append(f'   Selectors: {selectors}')
        lines.append(f'   Encoding: {format_name}/{subtype}')
        lines.append(f'   Session: {destination / resolved_step.directory_name}')
    lines.append(
        f'Result: {destination / resolved[-1].directory_name / "session-record.jsonl"}'
    )
    return '\n'.join(lines) + '\n'


def _validate_record(path: Path) -> Path:
    path = path.resolve()
    if not path.is_file():
        raise RecsError(f'Session record does not exist: {path}')
    entries, errors = session_record.read_entries(path)
    if errors:
        raise RecsError('; '.join(errors))
    if not entries or not isinstance(entries[0], session_record.SessionHeader):
        raise RecsError(f'Session record has no initial header: {path}')
    return path


def _relative_path(path: Path, directory: Path) -> Path:
    try:
        return Path(os.path.relpath(path, directory))
    except ValueError:
        return path
