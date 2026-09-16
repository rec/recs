from pathlib import Path

import pytest

from recs.cfg.cfg import Cfg
from recs.ui.recording_summary import print_summary


@pytest.mark.parametrize(
    ('options', 'received', 'reason'),
    [
        ({'dry_run': True}, False, 'dry-run mode does not write files'),
        ({'calibrate': True}, False, 'calibration mode does not write files'),
        ({'silence_preview': True}, False, 'silence preview mode does not write files'),
        ({}, False, 'no audio updates were received'),
        (
            {},
            True,
            'audio stayed below the noise floor or candidate files were shorter '
            'than shortest_file_time',
        ),
    ],
)
def test_summary_explains_why_no_files_were_written(
    options: dict[str, bool],
    received: bool,
    reason: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    print_summary(Cfg(**options), 4.143, set(), [], received)
    assert capsys.readouterr().out == (
        'Recording time: 0:04.143\nFiles written: none\n'
        f'No files written because {reason}.\n'
    )


def test_summary_reports_failed_sources(capsys: pytest.CaptureFixture[str]) -> None:
    print_summary(Cfg(), 0, set(), ['B', 'A'], False)
    assert 'sources failed: A, B.' in capsys.readouterr().out


def test_summary_reports_removed_files(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    print_summary(Cfg(), 0, {tmp_path / 'missing.wav'}, [], True)
    assert (
        'all candidate files were removed or are no longer present.'
        in capsys.readouterr().out
    )
