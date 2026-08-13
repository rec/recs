import json
from pathlib import Path

import pytest

from recs.base.errors import RecsError
from recs.cfg import settings
from recs.cfg.cfg import Cfg


def test_settings_are_disabled_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv('RECS_DAEMON', raising=False)

    assert not Cfg().save_settings


def test_settings_are_enabled_for_daemon(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('RECS_DAEMON', '1')

    assert Cfg().save_settings


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
    path.write_text('{"attributes":{"recording.audio_buffer_seconds":4}}')

    with pytest.raises(RecsError, match='Immutable configuration attribute'):
        settings.load(Cfg(save_settings=True))
