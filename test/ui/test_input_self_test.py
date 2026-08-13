from pathlib import Path

import numpy as np
import pytest

from recs.cfg.cfg import Cfg
from recs.ui import input_self_test


class FakeRecorder:
    latest: 'FakeRecorder | None' = None

    def __init__(self, cfg: Cfg) -> None:
        self.cfg = cfg
        self.files_written: set[Path] = set()
        self.warnings: list[str] = []
        FakeRecorder.latest = self

    def run(self) -> None:
        pass

    def error_messages(self) -> list[str]:
        return self.warnings.copy()


def test_input_self_test_reports_file_levels(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    path = tmp_path / 'test.wav'
    path.touch()
    recorder = FakeRecorder(Cfg())
    recorder.files_written.add(path)
    recorder.warnings.append('quiet')
    monkeypatch.setattr(
        input_self_test.soundfile,
        'read',
        lambda path, always_2d: (np.array([[0.5], [-0.5]]), 48_000),
    )

    report = input_self_test._report(recorder)

    assert report.model_dump() == {
        'files': [
            {
                'path': path.as_posix(),
                'channels': 1,
                'sample_rate': 48_000,
                'peak': 0.5,
                'rms': 0.5,
            }
        ],
        'warnings': ['quiet'],
        'errors': [],
    }


def test_input_self_test_runs_record_everything_session(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(input_self_test, 'Recorder', FakeRecorder)

    assert input_self_test.main(['--include', 'Mic', '--seconds', '3']) == 0

    assert FakeRecorder.latest is not None
    cfg = FakeRecorder.latest.cfg
    assert cfg.selection.include == ['Mic']
    assert cfg.recording.record_everything is True
    assert cfg.recording.total_run_time == 3
    assert cfg.directory.output_directory == 'recs-self-test'
    assert capsys.readouterr().out == (
        '{\n  "files": [],\n  "warnings": [],\n  "errors": []\n}\n'
    )
