from pathlib import Path

import numpy as np
import pytest

from recs.cfg.cfg import Cfg
from recs.cfg.device import InputDevice
from recs.cfg.track import Track
from recs.ui import input_self_test, recording_session
from recs.ui.source_recorder import BufferStats


class FakeRecorder:
    latest: 'FakeRecorder | None' = None

    def __init__(self, cfg: Cfg) -> None:
        self.cfg = cfg
        self.session = recording_session.RecordingSession('fake', 0)
        self.warnings: list[str] = []
        FakeRecorder.latest = self

    def run(self) -> None:
        pass

    def error_messages(self) -> list[str]:
        return self.warnings.copy()


class FakeDevices:
    def __init__(self) -> None:
        source = InputDevice(
            {'name': 'Mic', 'max_input_channels': 2, 'default_samplerate': 48_000}
        )
        self.sources = {
            'Mic': FakeSource(
                name='Mic',
                source=source,
                tracks=[Track(source, '1'), Track(source, '2')],
            )
        }
        self.buffer_stats = {
            'Mic': BufferStats(
                dropped_blocks=1,
                dropped_frames=128,
                max_queued_seconds=0.25,
                max_write_seconds=0.125,
            )
        }


class FakeSource:
    def __init__(self, name: str, source: InputDevice, tracks: list[Track]) -> None:
        self.name = name
        self.source = source
        self.tracks = tracks


def test_input_self_test_reports_file_levels(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    path = tmp_path / 'test.wav'
    path.touch()
    recorder = FakeRecorder(Cfg())
    recorder._devices = FakeDevices()
    recorder.session.files_written.add(path)
    recorder.warnings.append('quiet')
    monkeypatch.setattr(
        input_self_test.soundfile,
        'read',
        lambda path, always_2d: (np.array([[0.5, 0.25], [-0.5, -0.25]]), 48_000),
    )

    report = input_self_test._report(recorder)

    assert report.model_dump() == {
        'devices': [
            {
                'name': 'Mic',
                'channels': 2,
                'sample_rate': 48_000,
                'tracks': [
                    {'name': '1', 'channels': [1]},
                    {'name': '2', 'channels': [2]},
                ],
            }
        ],
        'files': [
            {
                'path': path.as_posix(),
                'channels': 2,
                'sample_rate': 48_000,
                'peak': 0.5,
                'rms': 0.39528470752104744,
                'channel_peaks': [0.5, 0.25],
                'channel_rms': [0.5, 0.25],
            }
        ],
        'buffers': [
            {
                'source': 'Mic',
                'dropped_blocks': 1,
                'dropped_frames': 128,
                'max_queued_seconds': 0.25,
                'max_write_seconds': 0.125,
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
        '{\n'
        '  "devices": [],\n'
        '  "files": [],\n'
        '  "buffers": [],\n'
        '  "warnings": [],\n'
        '  "errors": []\n'
        '}\n'
    )
