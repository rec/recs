import argparse
import sys
from pathlib import Path

from . import session_record


def main(argv: list[str]) -> int:
    args = _parser().parse_args(argv)
    errors = check(args.path)
    for error in errors:
        print(error, file=sys.stderr)
    return int(bool(errors))


def check(path: Path) -> list[str]:
    try:
        record = session_record.read(path)
    except OSError as e:
        return [f'{path}: {e}']

    errors = list(record.errors)
    if not record.started_at:
        errors.append(f'{path}: missing header')
    if record.duration is None:
        errors.append(f'{path}: missing footer')
    elif record.duration < 0:
        errors.append(f'{path}: duration must be non-negative')
    started = _file_paths(
        path, [f.path for f in record.files if f.type == 'file_started']
    )
    finished = _file_paths(
        path, [f.path for f in record.files if f.type == 'file_finished']
    )
    for file in sorted(started - finished):
        errors.append(f'{path}: unfinished file {file.as_posix()}')
    started_records = {f.path: f for f in record.files if f.type == 'file_started'}
    for file in record.files:
        if not file.path:
            errors.append(f'{path}: file path must not be empty')
            continue
        if Path(file.path).is_absolute():
            errors.append(f'{path}: file path must be relative: {file.path}')
            continue
        file_path = _file_path(path, file.path)
        if not file_path.exists():
            errors.append(f'{path}: missing file {file.path}')
            continue
        errors.extend(_file_size_errors(path, file_path, file, started_records))
        errors.extend(_midi_file_errors(path, file_path, file))
    errors.extend(_frame_errors(path, record.files))
    errors.extend(_disk_switch_errors(path, record))
    return errors


def _file_size_errors(
    record_path: Path,
    file_path: Path,
    file: session_record.FileEntry,
    started: dict[str, session_record.FileEntry],
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
            f'{record_path}: {file.path} is smaller than '
            f'{frames} frames at {file.channels} channels/{file.bit_depth} bits'
        ]
    return []


def _frame_errors(
    record_path: Path, files: list[session_record.FileEntry]
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
            errors.append(f'{record_path}: {file.path} finishes before it starts')
            continue
        key = file.source, file.track
        previous = last_frame.get(key)
        if previous is not None and file.frame_count < previous:
            errors.append(
                f'{record_path}: frame count moved backwards for '
                f'{file.source or "unknown source"} track {file.track}'
            )
        last_frame[key] = file.frame_count
    return errors


def _midi_file_errors(
    record_path: Path, file_path: Path, file: session_record.FileEntry
) -> list[str]:
    if file.type != 'file_finished':
        return []
    if file.kind != 'midi' or not file.message_count:
        return []
    if file_path.stat().st_size:
        return []
    return [f'{record_path}: {file.path} has MIDI messages but is empty']


def _disk_switch_errors(
    record_path: Path, record: session_record.SessionRecord
) -> list[str]:
    errors: list[str] = []
    if record.continued_from:
        if Path(record.continued_from).is_absolute():
            errors.append(f'{record_path}: continued_from must be relative')
        else:
            source = _file_path(record_path, record.continued_from)
            if not source.exists():
                errors.append(f'{record_path}: continued_from record is missing')
    for event in record.events:
        if event.type != 'disk_switch_continued_at' or event.continued_at is None:
            continue
        if Path(event.continued_at).is_absolute():
            errors.append(f'{record_path}: continued record path must be relative')
            continue
        continued = _file_path(record_path, event.continued_at)
        if not continued.exists():
            errors.append(f'{record_path}: continued record is missing')
            continue
        try:
            next_record = session_record.read(continued)
        except OSError as e:
            errors.append(f'{record_path}: continued record cannot be read: {e}')
            continue
        if next_record.continued_from != str(record_path):
            errors.append(f'{continued}: continued_from does not point back')
    return errors


def _file_paths(record_path: Path, paths: list[str]) -> set[Path]:
    return {_file_path(record_path, p) for p in paths}


def _file_path(record_path: Path, path: str) -> Path:
    return record_path.parent / Path(path)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog='recs record check')
    subparsers = parser.add_subparsers(dest='command', required=True)
    check_parser = subparsers.add_parser('check')
    check_parser.add_argument('path', type=Path)
    return parser
