import json
from pathlib import Path

import numpy as np
import pytest
import soundfile
import tdir
from pytest_regressions.data_regression import DataRegressionFixture

from recs.base.types import Format
from recs.cfg import Cfg, run_cli

from .conftest import DEVICES
from .recs_runner import RecsRunner

EVENT_COUNT = 218
EVENT_COUNT_SINGLE = 75


TESTDATA = Path(__file__).parent / 'testdata/end_to_end'
FILE_INPUTS = Path(__file__).parent / 'testdata/file_inputs'
REPO_ROOT = Path(__file__).resolve().parent.parent

CASES = (
    ('default', {}, EVENT_COUNT),
    ('default', {'dry_run': True, 'silent': True}, EVENT_COUNT),
    ('single', {'include': ['flow'], 'silent': True}, EVENT_COUNT_SINGLE),
    ('time', {'output_directory': '{sdate}', 'silent': True}, EVENT_COUNT),
    (
        'device_channel',
        {'output_directory': '{device}/{channel}', 'silent': True},
        EVENT_COUNT,
    ),
)


@pytest.mark.parametrize('name, cfg, event_count', CASES)
@tdir
def test_end_to_end(name, cfg, event_count, mock_mp, mock_devices, monkeypatch):
    test_case = RecsRunner(cfg, monkeypatch, event_count)
    test_case.run()

    events = sorted(test_case.events())
    events = [(int(o * 1_000_000), s.channels) for o, s in events]
    assert len(events) == event_count

    if test_case.cfg.general.dry_run:
        assert not test_case.paths()
        return

    test_case.assert_matches(TESTDATA / name)


def test_info(mock_input_streams, capsys):
    run_cli.run_cli(Cfg(info=True))
    data = capsys.readouterr().out

    actual = json.loads(data)
    assert actual == DEVICES


@tdir
def test_file_inputs(
    data_regression: DataRegressionFixture,
    mock_mp: None,
    capsys: pytest.CaptureFixture[str],
) -> None:
    files = [FILE_INPUTS / 'mono.wav', FILE_INPUTS / 'stereo.wav']
    run_cli.run_cli(
        Cfg(
            files=files,
            output_directory='files',
            quiet_after_end=0,
            quiet_before_start=0,
            shortest_file_time=0,
            silent=True,
        )
    )

    outputs = sorted(Path('files').glob(f'*.{Format.wav}'))
    assert [path.name for path in outputs] == ['mono-1.wav', 'stereo-1.wav']

    manifest = json.loads(Path('files/recs-session.json').read_text())
    data_regression.check(
        _stable_manifest(manifest),
        basename='file_inputs_manifest',
    )

    for source, output in zip(files, outputs, strict=True):
        source_audio, source_samplerate = soundfile.read(source)
        output_audio, output_samplerate = soundfile.read(output)
        assert output_samplerate == source_samplerate
        assert np.allclose(output_audio, source_audio)

    summary = capsys.readouterr().out
    assert summary.startswith('Recording time: ')
    assert summary.endswith(
        'Files written:\n'
        '  files/mono-1.wav\n'
        '  files/stereo-1.wav\n'
    )


def _stable_manifest(manifest: dict[str, object]) -> dict[str, object]:
    result = manifest | {
        'started_at': '<timestamp>',
        'ended_at': '<timestamp>',
        'duration': '<duration>',
    }
    for file in result['files']:
        assert isinstance(file, dict)
        file['source'] = str(Path(str(file['source'])).relative_to(REPO_ROOT))
    return result
