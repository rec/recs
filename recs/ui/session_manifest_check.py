import argparse
import sys
from pathlib import Path

from . import session_manifest


def main(argv: list[str]) -> int:
    args = _parser().parse_args(argv)
    errors = check(args.path)
    for error in errors:
        print(error, file=sys.stderr)
    return int(bool(errors))


def check(path: Path) -> list[str]:
    try:
        manifest = session_manifest.read(path)
    except OSError as e:
        return [f'{path}: {e}']

    errors = list(manifest.errors)
    if not manifest.started_at:
        errors.append(f'{path}: missing header')
    if manifest.duration is None:
        errors.append(f'{path}: missing footer')
    elif manifest.duration < 0:
        errors.append(f'{path}: duration must be non-negative')
    started = _file_paths(
        path, [f.path for f in manifest.files if f.type == 'file_started']
    )
    finished = _file_paths(
        path, [f.path for f in manifest.files if f.type == 'file_finished']
    )
    for file in sorted(started - finished):
        errors.append(f'{path}: unfinished file {file.as_posix()}')
    for file in manifest.files:
        if not file.path:
            errors.append(f'{path}: file path must not be empty')
            continue
        file_path = _file_path(path, file.path)
        if not file_path.exists():
            errors.append(f'{path}: missing file {file.path}')
    return errors


def _file_paths(manifest_path: Path, paths: list[str]) -> set[Path]:
    return {_file_path(manifest_path, p) for p in paths}


def _file_path(manifest_path: Path, path: str) -> Path:
    result = Path(path)
    if result.is_absolute():
        return result
    return manifest_path.parent / result


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog='recs manifest check')
    subparsers = parser.add_subparsers(dest='command', required=True)
    check_parser = subparsers.add_parser('check')
    check_parser.add_argument('path', type=Path)
    return parser
