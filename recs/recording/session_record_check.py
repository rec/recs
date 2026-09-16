import sys
from pathlib import Path
from typing import Annotated

import tyro
from pydantic import BaseModel
from soundfile import SoundFileError

from ..base.errors import RecsError
from .files import verify_recording
from .read import read_recording_chain


class CheckCli(BaseModel, frozen=True):
    path: Annotated[Path, tyro.conf.Positional]


def main(argv: list[str]) -> int:
    config = tyro.extras.subcommand_cli_from_dict(
        {'check': CheckCli},
        args=argv,
        prog='recs record',
        description='Validate recording documents and their media, not start capture.',
    )
    errors = check(config.path)
    for error in errors:
        print(error, file=sys.stderr)
    return int(bool(errors))


def check(path: Path) -> list[str]:
    errors: list[str] = []
    try:
        for record_path, document in read_recording_chain(path):
            result = verify_recording(document, record_path.parent)
            if document.body.state != 'sealed':
                errors.append(
                    f'{record_path}: recording is open; '
                    f'{len(document.body.unfinished_files)} unfinished files'
                )
            if result.unresolved_audio_files:
                errors.append(
                    f'{record_path}: {result.unresolved_audio_files} audio files '
                    'have unresolved timeline placement'
                )
    except (OSError, RecsError, ValueError, EOFError, SoundFileError) as error:
        errors.append(f'{path}: {type(error).__name__}: {error}')
    return errors
