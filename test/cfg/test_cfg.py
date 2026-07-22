from pathlib import Path

import pytest
from pydantic import ValidationError

from recs.base.types import RecordKeys
from recs.cfg import Cfg, cfg
from test.conftest import DEVICES_FILE


def test_sdtype(mock_devices):
    Cfg(formats=['wav'], subtype='pcm_16', sdtype='int32')


def test_missing_files(mock_devices: None) -> None:
    with pytest.raises(ValidationError, match='Non-existent file: unknown.wav'):
        Cfg(files=['unknown.wav'])


def test_bad_devices(mock_devices):
    with pytest.raises(ValidationError, match='unknown.json does not exist'):
        Cfg(devices=Path('unknown.json'))


def test_empty_devices(tmp_path: Path, mock_devices: None) -> None:
    devices = tmp_path / 'devices.json'
    devices.write_text('[]')

    with pytest.raises(ValidationError, match='contains no devices'):
        Cfg(devices=devices)


def test_device_profiles_apply_to_matching_device(
    tmp_path: Path,
    mock_devices: None,
) -> None:
    profiles = tmp_path / 'profiles.json'
    profiles.write_text(
        '{"Mic": {"noise_floor": 42, "recording": {"quiet_after_end": 5}}}'
    )

    profiled = Cfg(profiles=profiles).with_device_profile('Mic')
    unprofiled = Cfg(profiles=profiles).with_device_profile('Other')

    assert profiled.recording.noise_floor == 42
    assert profiled.recording.quiet_after_end == 5
    assert profiled.recording.quiet_before_start == 1
    assert unprofiled.recording.noise_floor == 70


def test_device_profile_noise_floor_overrides_global_default(
    tmp_path: Path,
    mock_devices: None,
) -> None:
    profiles = tmp_path / 'profiles.json'
    profiles.write_text('{"Mic": {"recording": {"noise_floor": 42}}}')

    profiled = Cfg(noise_floor=80, profiles=profiles).with_device_profile('Mic')
    unprofiled = Cfg(noise_floor=80, profiles=profiles).with_device_profile('Other')

    assert profiled.recording.noise_floor == 42
    assert unprofiled.recording.noise_floor == 80


def test_unknown_device_profile_field_is_validation_error(
    tmp_path: Path,
    mock_devices: None,
) -> None:
    profiles = tmp_path / 'profiles.json'
    profiles.write_text('{"Mic": {"unknown": true}}')

    with pytest.raises(ValueError, match='Unknown profile field'):
        Cfg(profiles=profiles).with_device_profile('Mic')


def test_unknown_config_field_is_validation_error(mock_devices: None) -> None:
    with pytest.raises(ValidationError, match='Extra inputs are not permitted'):
        Cfg(unknown=True)


@pytest.mark.parametrize('field', ['sleep_time_device', 'ui_refresh_rate'])
def test_console_rates_must_be_positive(field: str, mock_devices: None) -> None:
    with pytest.raises(ValidationError, match='must be positive'):
        Cfg(**{field: 0})


@pytest.mark.parametrize('field', ['audio_buffer_seconds', 'buffer_status_period'])
def test_buffer_times_must_be_positive(field: str, mock_devices: None) -> None:
    with pytest.raises(ValidationError, match='must be positive'):
        Cfg(**{field: 0})


def test_buffer_warning_fraction_must_be_fraction(mock_devices: None) -> None:
    with pytest.raises(ValidationError, match='must be between 0 and 1'):
        Cfg(buffer_warning_fraction=2)


def test_minimum_free_space_must_not_be_negative(mock_devices: None) -> None:
    with pytest.raises(ValidationError, match='must be non-negative'):
        Cfg(minimum_free_space=-1)


def test_key_labels_parse_to_label_map(mock_devices: None) -> None:
    cfg = Cfg(key_label=['g=guitar too soft', 'd=drums too soft'])

    assert cfg.keys.labels == {'g': 'guitar too soft', 'd': 'drums too soft'}


def test_key_labels_must_have_labels(mock_devices: None) -> None:
    with pytest.raises(ValidationError, match='key_label must look like key=label'):
        Cfg(key_label=['g'])


def test_devices(mock_devices):
    cfg = Cfg(devices=DEVICES_FILE)
    assert cfg.input_devices


def test_gui_defaults_to_all_key_events(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cfg, '_pynput_available', lambda: False)

    c = Cfg(gui=True)

    assert c.keys.record_keys == RecordKeys.all
    assert c.keys.record_key_all_apps is True


def test_terminal_defaults_to_all_key_events_when_pynput_is_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(cfg, '_pynput_available', lambda: True)

    c = Cfg()

    assert c.keys.record_keys == RecordKeys.all
    assert c.keys.record_key_all_apps is False


def test_terminal_without_pynput_defaults_to_key_presses(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(cfg, '_pynput_available', lambda: False)

    c = Cfg()

    assert c.keys.record_keys == RecordKeys.press
    assert c.keys.record_key_all_apps is False


def test_terminal_without_pynput_rejects_all_key_events(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(cfg, '_pynput_available', lambda: False)

    with pytest.raises(ValidationError, match='record_keys cannot be all'):
        Cfg(record_keys=RecordKeys.all)
