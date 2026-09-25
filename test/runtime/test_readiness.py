import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from ufor.encoding import Format, Subtype

from recs.cfg import device, projects, settings
from recs.cfg.cfg import Cfg
from recs.runtime import readiness
from recs.runtime.recorder import Recorder


@pytest.fixture(autouse=True)
def inspection_only(monkeypatch: pytest.MonkeyPatch, mock_devices: None) -> None:
    def unexpected(*args: object, **kwargs: object) -> None:
        pytest.fail('Readiness must not start a recorder or open an input stream')

    monkeypatch.setattr(Recorder, '__init__', unexpected)
    monkeypatch.setattr(device.InputDevice, 'input_stream', unexpected)
    monkeypatch.setattr(
        readiness.shutil,
        'disk_usage',
        lambda path: SimpleNamespace(free=4_000_000_000),
    )


def test_readiness_collects_independent_problems(tmp_path: Path) -> None:
    blocker = tmp_path / 'file'
    blocker.write_text('not a directory')
    cfg = Cfg(include=['absent', 'Mic+2'], output_directory=str(blocker / 'session'))

    report = readiness.inspect_configuration(settings.LoadedSettings(cfg=cfg))

    assert any('absent' in w for w in report.warnings)
    assert any('only 1 channel' in e for e in report.failures)
    assert any('not a directory' in e for e in report.failures)
    assert list(tmp_path.iterdir()) == [blocker]


def test_missing_devices_warn_without_failing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    result = readiness.main(
        [
            '--json-output',
            '--',
            '--include',
            'absent',
            '--output-directory',
            str(tmp_path),
        ]
    )

    report = json.loads(capsys.readouterr().out)
    assert result == 0
    assert report['sources'] == []
    assert report['failures'] == []
    assert any('absent' in w for w in report['warnings'])
    assert not list(tmp_path.iterdir())


def test_missing_alias_does_not_hide_present_tracks(tmp_path: Path) -> None:
    cfg = Cfg(
        alias=['vocal=absent', 'room=Mic'],
        include=['vocal', 'room'],
        output_directory=str(tmp_path),
    )
    report = readiness.inspect_configuration(settings.LoadedSettings(cfg=cfg))
    assert report.failures == []
    assert [s.name for s in report.sources] == ['Mic']
    assert any('vocal' in w for w in report.warnings)


def test_readiness_uses_project_overlay_and_explicit_overrides(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(projects, 'projects_directory', lambda: tmp_path / 'projects')
    monkeypatch.setattr(
        settings,
        'mutable_settings_path',
        lambda project_name=None: tmp_path / 'overlay.json',
    )
    cfg = Cfg(
        include=['Flower'], save_settings=True, output_directory=str(tmp_path / 'audio')
    )
    projects.save(projects.Project(name='show', cfg=cfg))
    settings.save(
        cfg.set_attr('recording.noise_floor', 42),
        {'Flower 8': {'Room': 1}},
        {},
        project_name='show',
    )

    result = readiness.main(
        ['--project-name', 'show', '--json-output', '--', '--noise-floor', '35']
    )
    report = json.loads(capsys.readouterr().out)
    assert result == 0
    assert report['settings']['recording']['noise_floor'] == 35
    assert report['sources'][0]['tracks'][0]['name'] == 'Room'
    assert not (tmp_path / 'audio').exists()

    readiness.main(['--project-name', 'show', '--json-output'])
    report = json.loads(capsys.readouterr().out)
    assert report['settings']['recording']['noise_floor'] == 42


def test_effective_formats_and_storage_estimate(tmp_path: Path) -> None:
    report = readiness.inspect_configuration(
        settings.LoadedSettings(
            cfg=Cfg(
                include=['Mic'], output_directory=str(tmp_path), minimum_free_space=0
            )
        )
    )
    assert report.failures == []
    assert report.sources[0].tracks[0].channels == [1]
    assert report.sources[0].settings['audio']['formats'] == ['flac']
    assert report.input_pcm_bytes_per_second == 48_000 * 4
    assert report.input_pcm_seconds == report.free_bytes / (48_000 * 4)
    assert any('actual duration unknown' in s for s in report.limitations)


@pytest.mark.parametrize('channels', [[0], [2], [1, 1]])
def test_invalid_saved_layout_fails(tmp_path: Path, channels: list[int]) -> None:
    report = readiness.inspect_configuration(
        settings.LoadedSettings(
            cfg=Cfg(include=['Mic'], output_directory=str(tmp_path)),
            tracks={'Mic': [settings.TrackSettings(channels=channels)]},
        )
    )
    assert any('invalid saved channel layout' in e for e in report.failures)


def test_readiness_help_does_not_discover_devices(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unexpected() -> None:
        pytest.fail('Help must not discover devices')

    monkeypatch.setattr(device, 'query_devices', unexpected)
    with pytest.raises(SystemExit) as error:
        readiness.main(['--help'])
    assert error.value.code == 0


def test_text_and_json_report_the_same_failure(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    arguments = ['--', '--include', 'Mic+2', '--output-directory', str(tmp_path)]
    assert readiness.main(['--json-output', *arguments]) == 1
    report = json.loads(capsys.readouterr().out)
    assert readiness.main(arguments) == 1
    output = capsys.readouterr().out
    for message in report['failures']:
        assert f'FAIL: {message}' in output
    for message in report['warnings']:
        assert f'WARN: {message}' in output


def test_unknown_project_has_structured_failure(
    capsys: pytest.CaptureFixture[str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(projects, 'projects_directory', lambda: tmp_path)
    assert readiness.main(['--project-name', 'absent', '--json-output']) == 1
    report = json.loads(capsys.readouterr().out)
    assert report['failures'] == ['Unknown recording project: absent']


def test_invalid_output_pattern_fails(tmp_path: Path) -> None:
    report = readiness.inspect_configuration(
        settings.LoadedSettings(
            cfg=Cfg(include=['Mic'], output_directory=str(tmp_path / '{unknown}')),
        )
    )
    assert any('Unknown: unknown' in e for e in report.failures)
    assert not list(tmp_path.iterdir())


def test_every_requested_encoding_is_checked(tmp_path: Path) -> None:
    report = readiness.inspect_configuration(
        settings.LoadedSettings(
            cfg=Cfg(
                include=['Mic'],
                output_directory=str(tmp_path),
                formats=[Format.wav, Format.flac],
                subtype=Subtype.float,
            )
        )
    )
    assert any('flac/float' in e for e in report.failures)
