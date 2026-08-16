import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from recs.base import times
from recs.cfg.cfg import Cfg
from recs.daemon import gui_ipc
from recs.misc import legal_filename


def with_default_output_directory(cfg: Cfg, timestamp: float) -> Cfg:
    if cfg.directory.output_directory:
        return cfg

    if (record_directory := daemon_record_directory(cfg)) is not None:
        output_directory = record_directory
    else:
        output_directory = available_directory(Path(session_directory_name(timestamp)))

    directory = cfg.directory.model_copy(
        update={'output_directory': str(output_directory)}
    )
    result = cfg.model_copy(update={'directory': directory})
    result.__dict__.pop('output_path_pattern', None)
    return result


def daemon_record_directory(cfg: Cfg) -> Path | None:
    if not gui_ipc.daemon_mode_enabled():
        return None
    path = legal_filename.legal_path(Path(cfg.general.default_record_directory))
    if path.is_absolute():
        return path
    return record_disk() / path


def record_disk() -> Path:
    disks = mounted_record_disks()
    if not disks:
        return Path.home()
    return max(disks, key=lambda p: shutil.disk_usage(p).free)


def timestamp_or_now(timestamp: float | None) -> float:
    return times.timestamp() if timestamp is None else timestamp


def mounted_record_disks() -> list[Path]:
    if os.name == 'nt':
        return windows_record_disks()

    disks: list[Path] = []
    for parent in record_disk_parents():
        try:
            children = list(parent.iterdir())
        except OSError:
            continue
        disks.extend(p for p in children if p.is_dir() and p.is_mount())
    return disks


def record_disk_parents() -> list[Path]:
    parents = [Path('/Volumes'), Path('/media'), Path('/mnt')]
    user = os.environ.get('USER')
    if user:
        parents.append(Path('/run/media') / user)
    return parents


def windows_record_disks() -> list[Path]:
    system = Path.home().anchor.lower()
    disks = []
    for letter in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ':
        path = Path(f'{letter}:/')
        if path.exists() and path.anchor.lower() != system:
            disks.append(path)
    return disks


def available_directory(path: Path) -> Path:
    if not path.exists():
        return path

    index = 1
    while True:
        candidate = path.with_name(f'{path.name}_{index}')
        if not candidate.exists():
            return candidate
        index += 1


def session_directory_name(timestamp: float) -> str:
    return legal_filename.legal_filename(
        datetime.fromtimestamp(timestamp).strftime('recs: %Y-%m-%d %H:%M:%S')
    )


def manifest_directory(output_directory: str, timestamp: float) -> Path:
    ts = datetime.fromtimestamp(timestamp)
    try:
        return legal_filename.legal_path(
            Path(ts.strftime(output_directory).format(**manifest_times(ts)))
        )
    except KeyError:
        prefix = output_directory.split('{', 1)[0].rstrip('/\\')
        return legal_filename.legal_path(Path(prefix or '.'))


def audio_directory(output_directory: str, timestamp: float) -> Path:
    return manifest_directory(output_directory, timestamp) / 'audio'


def midi_directory(output_directory: str, timestamp: float) -> Path:
    return manifest_directory(output_directory, timestamp) / 'midi'


def existing_parent(path: Path) -> Path:
    for candidate in (path, *path.parents):
        if candidate.exists():
            return candidate
    return Path()


def write_text_atomically(path: Path, content: str) -> None:
    tmp = path.with_name(f'.{path.name}.tmp')
    with tmp.open('w') as fp:
        fp.write(content)
        fp.flush()
        os.fsync(fp.fileno())
    tmp.replace(path)


def open_folder(path: Path) -> None:
    commands = {
        'darwin': ['open', str(path)],
        'win32': ['explorer', str(path)],
    }
    command = commands.get(sys.platform, ['xdg-open', str(path)])
    subprocess.run(command, check=False)


def manifest_times(ts: datetime) -> dict[str, str]:
    return {
        'date': ts.strftime('%Y%m%d'),
        'ddate': ts.strftime('%Y-%m-%d'),
        'dtime': ts.strftime('%H:%M:%S'),
        'hour': ts.strftime('%H'),
        'minute': ts.strftime('%M'),
        'month': ts.strftime('%m'),
        'sdate': ts.strftime('%Y-%m-%d'),
        'second': ts.strftime('%S'),
        'stime': ts.strftime('%H-%M-%S'),
        'time': ts.strftime('%H%M%S'),
        'timestamp': ts.isoformat(),
        'year': ts.strftime('%Y'),
    }
