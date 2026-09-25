from pathlib import Path

import pytest

from recs.base.errors import RecsError
from recs.cfg import projects, settings
from recs.cfg.cfg import Cfg
from recs.daemon import control_cli


def test_project_round_trip_and_cli_overrides(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(projects, 'projects_directory', lambda: tmp_path)
    project = projects.RecordingProject(
        name='show',
        cfg=Cfg(include=['Mic'], formats=['flac'], output_directory='recordings'),
        track_names={'Mic': {'Voice': 1}},
        tracks={'Mic': [settings.TrackSettings(channels=[1, 2])]},
        links=['https://example.com'],
        templates={'index': '<h1>Show</h1>'},
    )

    path = projects.save(project)
    loaded = projects.configured('show', ['--output-directory', 'other'])

    assert path == tmp_path / 'show.json'
    assert loaded.cfg.selection.include == ['Mic']
    assert loaded.cfg.audio.formats == ['flac']
    assert loaded.cfg.directory.output_directory == 'other'
    assert loaded.track_names == {'Mic': {'Voice': 1}}
    assert loaded.tracks == {'Mic': [settings.TrackSettings(channels=[1, 2])]}
    assert loaded.project_name == 'show'
    assert projects.load('show') == project


def test_project_refuses_replacement_and_invalid_names(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(projects, 'projects_directory', lambda: tmp_path)
    project = projects.RecordingProject(name='show', cfg=Cfg())
    projects.save(project)

    with pytest.raises(RecsError, match='already exists'):
        projects.save(project)
    with pytest.raises(RecsError, match='Invalid recording project name'):
        projects.project_path('../show')
    with pytest.raises(RecsError, match='Invalid recording project name'):
        projects.project_path('-default-')


def test_project_argument_is_removed_before_cfg_parsing() -> None:
    assert projects.project_argument(
        ['--include', 'Mic', '--project-name', 'show', '--silent']
    ) == ('show', ['--include', 'Mic', '--silent'])
    assert projects.project_argument(['--project-name=show']) == ('show', [])


def test_daemon_projects_are_separate_from_user_projects(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv('HOME', str(tmp_path))
    monkeypatch.delenv('RECS_DAEMON', raising=False)

    user_directory = projects.projects_directory()

    monkeypatch.setenv('RECS_DAEMON', '1')

    assert user_directory == tmp_path / '.config/recs/projects'
    assert projects.projects_directory() == tmp_path / '.config/recs/daemon-projects'


def test_project_commands_save_list_show_and_use(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(projects, 'projects_directory', lambda: tmp_path)
    monkeypatch.setattr(settings, 'settings_path', lambda: tmp_path / 'settings.json')
    used: list[settings.LoadedSettings] = []
    monkeypatch.setattr(
        projects.run_cli,
        'run_cli',
        lambda cfg, loaded: used.append(loaded),
    )

    assert projects.main(['save', 'show', '--', '--include', 'Mic']) == 0
    assert projects.main(['list']) == 0
    assert projects.main(['show', 'show']) == 0
    assert projects.main(['use', 'show']) == 0

    output = capsys.readouterr().out
    assert str(tmp_path / 'show.json') in output
    assert '\nshow\n' in output
    assert '"include": [' in output
    assert used[0].cfg.selection.include == ['Mic']


def test_project_switch_uses_the_running_recorder(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[list[str]] = []
    monkeypatch.setattr(
        control_cli, 'main', lambda arguments: calls.append(arguments) or 0
    )

    assert projects.main(['switch', 'show']) == 0
    assert projects.main(['switch']) == 0

    with pytest.raises(RecsError, match='at most one'):
        projects.main(['switch', 'one', 'two'])

    assert calls == [['project-switch', 'show'], ['project-switch']]
