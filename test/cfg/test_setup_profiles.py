from pathlib import Path

import pytest

from recs.base.errors import RecsError
from recs.cfg import settings, setup_profiles
from recs.cfg.cfg import Cfg


def test_setup_profile_round_trip_and_cli_overrides(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(setup_profiles, 'profiles_directory', lambda: tmp_path)
    profile = setup_profiles.SetupProfile(
        cfg=Cfg(include=['Mic'], formats=['flac'], output_directory='recordings'),
        track_names={'Mic': {'Voice': 1}},
        tracks={'Mic': [settings.TrackSettings(channels=[1, 2])]},
    )

    path = setup_profiles.save('show', profile)
    loaded = setup_profiles.configured('show', ['--output-directory', 'other'])

    assert path == tmp_path / 'show.json'
    assert loaded.cfg.selection.include == ['Mic']
    assert loaded.cfg.audio.formats == ['flac']
    assert loaded.cfg.directory.output_directory == 'other'
    assert loaded.track_names == {'Mic': {'Voice': 1}}
    assert loaded.tracks == {'Mic': [settings.TrackSettings(channels=[1, 2])]}


def test_setup_profile_refuses_replacement_and_invalid_names(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(setup_profiles, 'profiles_directory', lambda: tmp_path)
    profile = setup_profiles.SetupProfile(cfg=Cfg())
    setup_profiles.save('show', profile)

    with pytest.raises(RecsError, match='already exists'):
        setup_profiles.save('show', profile)
    with pytest.raises(RecsError, match='Invalid recording setup name'):
        setup_profiles.profile_path('../show')


def test_profile_argument_is_removed_before_cfg_parsing() -> None:
    assert setup_profiles.profile_argument(
        ['--include', 'Mic', '--profile', 'show', '--silent']
    ) == ('show', ['--include', 'Mic', '--silent'])
    assert setup_profiles.profile_argument(['--profile=show']) == ('show', [])


def test_profile_commands_save_list_show_and_use(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(setup_profiles, 'profiles_directory', lambda: tmp_path)
    monkeypatch.setattr(settings, 'settings_path', lambda: tmp_path / 'settings.json')
    used: list[settings.LoadedSettings] = []
    monkeypatch.setattr(
        setup_profiles.run_cli,
        'run_cli',
        lambda cfg, loaded: used.append(loaded),
    )

    assert setup_profiles.main(['save', 'show', '--', '--include', 'Mic']) == 0
    assert setup_profiles.main(['list']) == 0
    assert setup_profiles.main(['show', 'show']) == 0
    assert setup_profiles.main(['use', 'show']) == 0

    output = capsys.readouterr().out
    assert str(tmp_path / 'show.json') in output
    assert '\nshow\n' in output
    assert '"include": [' in output
    assert used[0].cfg.selection.include == ['Mic']
