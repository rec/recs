"""Final human-readable recording report, independent of runtime orchestration."""

from pathlib import Path

from recs.base import times
from recs.cfg.cfg import Cfg


def print_summary(
    cfg: Cfg,
    elapsed: float,
    files_written: set[Path],
    failed: list[str],
    received_audio: bool,
) -> None:
    duration = times.to_str(elapsed)
    if elapsed < 60:
        duration = f'0:{duration:0>6}'
    print(f'Recording time: {duration}')
    files = sorted(p for p in files_written if p.exists())
    if files:
        print('Files written:')
        for path in files:
            print(f'  {path}')
    else:
        print('Files written: none')
        reason = _no_files_reason(cfg, bool(files_written), failed, received_audio)
        print(f'No files written because {reason}.')


def _no_files_reason(
    cfg: Cfg, had_files: bool, failed: list[str], received_audio: bool
) -> str:
    if cfg.general.dry_run:
        return 'dry-run mode does not write files'
    if cfg.general.calibrate:
        return 'calibration mode does not write files'
    if cfg.general.silence_preview:
        return 'silence preview mode does not write files'
    if failed:
        return f'sources failed: {", ".join(sorted(failed))}'
    if had_files:
        return 'all candidate files were removed or are no longer present'
    if not received_audio:
        return 'no audio updates were received'
    return (
        'audio stayed below the noise floor or candidate files were shorter '
        'than shortest_file_time'
    )
