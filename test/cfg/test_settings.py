import json
from pathlib import Path

import pytest
from reccy.configuration import units

from recs.base.errors import RecsError
from recs.cfg import settings
from recs.cfg.cfg import Cfg
from recs.musicians import Musician, SourceMusician


def test_settings_are_enabled_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv('RECS_DAEMON', raising=False)

    assert Cfg().save_settings


def test_settings_are_enabled_for_daemon(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('RECS_DAEMON', '1')

    assert Cfg().save_settings


def test_user_and_daemon_settings_are_separate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv('HOME', str(tmp_path))
    user_cfg = Cfg(save_settings=True).set_attr('recording.noise_floor', 42)
    daemon_cfg = Cfg(save_settings=True).set_attr('recording.noise_floor', 43)

    settings.save(user_cfg, {}, {}, daemon=False)
    settings.save(daemon_cfg, {}, {}, daemon=True)

    assert settings.settings_path(daemon=False) == (
        tmp_path / '.config/recs/settings.json'
    )
    assert settings.settings_path(daemon=True) == (
        tmp_path / '.config/recs/daemon-settings.json'
    )
    user_loaded = settings.load(Cfg(save_settings=True), daemon=False)
    daemon_loaded = settings.load(Cfg(save_settings=True), daemon=True)
    assert user_loaded.cfg.recording.noise_floor == 42
    assert daemon_loaded.cfg.recording.noise_floor == 43
    assert settings.project_settings_path('show', daemon=False) == (
        tmp_path / '.config/recs/project-settings/show.json'
    )
    assert settings.project_settings_path('show', daemon=True) == (
        tmp_path / '.config/recs/daemon-project-settings/show.json'
    )


def test_saved_settings_round_trip(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / 'settings.json'
    monkeypatch.setattr(settings, 'settings_path', lambda: path)
    cfg = Cfg(save_settings=True).set_attr('recording.noise_floor', 42)
    names = {'Ext': {'VL': 1}}
    tracks = {
        'Ext': [
            settings.TrackSettings(channels=[1]),
            settings.TrackSettings(channels=[2]),
        ]
    }

    settings.save(cfg, names, tracks)
    loaded = settings.load(Cfg(save_settings=True))

    assert loaded.cfg.recording.noise_floor == 42
    assert loaded.track_names == names
    assert loaded.tracks == tracks
    assert set(json.loads(path.read_text())['attributes']) == cfg.mutable_attributes
    assert not path.with_name('.settings.json.tmp').exists()


def test_saved_settings_preserve_musician_assignments(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / 'settings.json'
    monkeypatch.setattr(settings, 'settings_path', lambda: path)
    musicians = {
        'mike': Musician(name='mike', links=['insta:mike', 'mailto:mike@example.com'])
    }
    assignments = {'Ext': SourceMusician(musician='mike', channels=[1, 2])}

    settings.save(
        Cfg(save_settings=True),
        {},
        {},
        musicians=musicians,
        channel_musicians=assignments,
    )
    loaded = settings.load(Cfg(save_settings=True))

    assert loaded.musicians == musicians
    assert loaded.channel_musicians == assignments


def test_saved_settings_preserve_authored_units(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / 'settings.json'
    monkeypatch.setattr(settings, 'settings_path', lambda: path)
    cfg = Cfg(
        save_settings=True,
        quiet_before_start='250ms',
        quiet_after_end='1 min',
    )

    settings.save(cfg, {}, {})
    attributes = json.loads(path.read_text())['attributes']
    loaded = settings.load(Cfg(save_settings=True))

    assert attributes['recording.quiet_before_start'] == '250ms'
    assert attributes['recording.quiet_after_end'] == '1 min'
    provenance = units.collect_unit_provenance(loaded.cfg)
    assert provenance['/recording/quiet_before_start'].authored == '250ms'
    assert provenance['/recording/quiet_after_end'].authored == '1 min'


def test_saved_settings_keep_numeric_api_updates_numeric(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / 'settings.json'
    monkeypatch.setattr(settings, 'settings_path', lambda: path)
    cfg = Cfg(
        save_settings=True,
        quiet_before_start='250ms',
        quiet_after_end='1 min',
    ).set_attr('recording.quiet_before_start', 0.5)

    settings.save(cfg, {}, {})
    attributes = json.loads(path.read_text())['attributes']

    assert attributes['recording.quiet_before_start'] == 0.5
    assert attributes['recording.quiet_after_end'] == '1 min'


def test_cli_override_wins_over_saved_setting(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / 'settings.json'
    monkeypatch.setattr(settings, 'settings_path', lambda: path)
    settings.save(Cfg(save_settings=True).set_attr('recording.noise_floor', 42), {}, {})

    loaded = settings.load(
        Cfg(save_settings=True, noise_floor=60), {'recording.noise_floor'}
    )

    assert loaded.cfg.recording.noise_floor == 60


def test_cli_unit_provenance_wins_over_saved_setting(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / 'settings.json'
    monkeypatch.setattr(settings, 'settings_path', lambda: path)
    settings.save(Cfg(save_settings=True, quiet_before_start='1s'), {}, {})

    loaded = settings.load(
        Cfg(save_settings=True, quiet_before_start='250ms'),
        {'recording.quiet_before_start'},
    )

    provenance = units.collect_unit_provenance(loaded.cfg)
    assert provenance['/recording/quiet_before_start'].authored == '250ms'


def test_settings_allow_unavailable_profile_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / 'settings.json'
    monkeypatch.setattr(settings, 'settings_path', lambda: path)
    missing = tmp_path / 'unmounted' / 'profiles.json'
    settings.save(Cfg(save_settings=True, profiles=missing), {}, {})

    loaded = settings.load(Cfg(save_settings=True))

    assert loaded.cfg.device.profiles == missing


def test_settings_reject_immutable_attributes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / 'settings.json'
    monkeypatch.setattr(settings, 'settings_path', lambda: path)
    path.write_text('{"attributes":{"recording.memory_reserve_megabytes":4}}')

    with pytest.raises(RecsError, match='Immutable configuration attribute'):
        settings.load(Cfg(save_settings=True))


def test_project_settings_overlay_is_separate_from_global_settings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, 'settings_path', lambda: tmp_path / 'settings.json')
    monkeypatch.setattr(
        settings,
        'project_settings_path',
        lambda project_name: tmp_path / f'{project_name}.json',
    )
    settings.save(
        Cfg(save_settings=True).set_attr('recording.noise_floor', 42),
        {},
        {},
        project_name='second-interface',
    )

    loaded = settings.load(
        Cfg(save_settings=True),
        project_name='second-interface',
    )

    assert loaded.cfg.recording.noise_floor == 42
    assert loaded.project_name == 'second-interface'
    assert not (tmp_path / 'settings.json').exists()
