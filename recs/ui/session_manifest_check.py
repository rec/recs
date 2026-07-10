import argparse
import sys
from pathlib import Path

from pydantic import ValidationError

from .session_manifest import SessionManifest


def main(argv: list[str]) -> int:
    args = _parser().parse_args(argv)
    errors = check(args.path)
    for error in errors:
        print(error, file=sys.stderr)
    return int(bool(errors))


def check(path: Path) -> list[str]:
    try:
        manifest = SessionManifest.model_validate_json(path.read_text())
    except OSError as e:
        return [f'{path}: {e}']
    except ValidationError as e:
        return [f'{path}: {e}']

    errors: list[str] = []
    if manifest.duration < 0:
        errors.append(f'{path}: duration must be non-negative')
    for file in manifest.files:
        if not file.path:
            errors.append(f'{path}: file path must not be empty')
            continue
        file_path = Path(file.path)
        if not file_path.is_absolute():
            file_path = path.parent / file_path
        if not file_path.exists():
            errors.append(f'{path}: missing file {file.path}')
    return errors


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog='recs manifest check')
    subparsers = parser.add_subparsers(dest='command', required=True)
    check_parser = subparsers.add_parser('check')
    check_parser.add_argument('path', type=Path)
    return parser
