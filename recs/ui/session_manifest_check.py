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
    started_records = {f.path: f for f in manifest.files if f.type == 'file_started'}
    for file in manifest.files:
        if not file.path:
            errors.append(f'{path}: file path must not be empty')
            continue
        file_path = _file_path(path, file.path)
        if not file_path.exists():
            errors.append(f'{path}: missing file {file.path}')
            continue
        errors.extend(_file_size_errors(path, file_path, file, started_records))
        errors.extend(_midi_file_errors(path, file_path, file))
    errors.extend(_frame_errors(path, manifest.files))
    errors.extend(_disk_switch_errors(path, manifest))
    return errors


def _file_size_errors(
    manifest_path: Path,
    file_path: Path,
    file: session_manifest.ManifestFile,
    started: dict[str, session_manifest.ManifestFile],
) -> list[str]:
    if file.type != 'file_finished' or file.frame_count is None:
        return []
    if file.channels is None or file.bit_depth is None:
        return []
    if (start := started.get(file.path)) is None or start.frame_count is None:
        return []
    frames = file.frame_count - start.frame_count
    if frames < 0:
        return []
    expected_bytes = frames * file.channels * file.bit_depth // 8
    if file_path.stat().st_size < expected_bytes:
        return [
            f'{manifest_path}: {file.path} is smaller than '
            f'{frames} frames at {file.channels} channels/{file.bit_depth} bits'
        ]
    return []


def _frame_errors(
    manifest_path: Path, files: list[session_manifest.ManifestFile]
) -> list[str]:
    errors: list[str] = []
    started = {f.path: f for f in files if f.type == 'file_started'}
    last_frame: dict[tuple[str | None, int], int] = {}
    for file in files:
        if file.frame_count is None or file.track is None:
            continue
        if (
            file.type == 'file_finished'
            and (start := started.get(file.path)) is not None
            and start.frame_count is not None
            and file.frame_count < start.frame_count
        ):
            errors.append(f'{manifest_path}: {file.path} finishes before it starts')
            continue
        key = file.source, file.track
        previous = last_frame.get(key)
        if previous is not None and file.frame_count < previous:
            errors.append(
                f'{manifest_path}: frame count moved backwards for '
                f'{file.source or "unknown source"} track {file.track}'
            )
        last_frame[key] = file.frame_count
    return errors


def _midi_file_errors(
    manifest_path: Path, file_path: Path, file: session_manifest.ManifestFile
) -> list[str]:
    if file.type != 'file_finished':
        return []
    if file.kind != 'midi' or not file.message_count:
        return []
    if file_path.stat().st_size:
        return []
    return [f'{manifest_path}: {file.path} has MIDI messages but is empty']


def _disk_switch_errors(
    manifest_path: Path, manifest: session_manifest.SessionManifest
) -> list[str]:
    errors: list[str] = []
    if manifest.continued_from:
        source = _file_path(manifest_path, manifest.continued_from)
        if not source.exists():
            errors.append(f'{manifest_path}: continued_from manifest is missing')
    for event in manifest.events:
        if event.type != 'disk_switch_continued_at' or event.continued_at is None:
            continue
        continued = _file_path(manifest_path, event.continued_at)
        if not continued.exists():
            errors.append(f'{manifest_path}: continued manifest is missing')
            continue
        try:
            next_manifest = session_manifest.read(continued)
        except OSError as e:
            errors.append(f'{manifest_path}: continued manifest cannot be read: {e}')
            continue
        if next_manifest.continued_from != str(manifest_path):
            errors.append(f'{continued}: continued_from does not point back')
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
