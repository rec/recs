from pathlib import Path
from test.conftest import DEVICES_FILE

import pytest
from pydantic import ValidationError

from recs.base.types import MidiTiming, RecordKeys
from recs.cfg import cfg
from recs.cfg.cfg import Cfg


def test_sdtype(mock_devices):
    Cfg(formats=['wav'], subtype='pcm_16', sdtype='int32')


def test_band_mode_is_disabled_by_default(mock_devices: None) -> None:
    assert not Cfg().recording.band_mode


def test_ui_refresh_default_is_conservative(mock_devices: None) -> None:
    assert Cfg().console.ui_refresh_rate == 10


def test_midi_recording_is_enabled_by_default(mock_devices: None) -> None:
    cfg = Cfg()

    assert cfg.midi.record_midi
    assert cfg.midi.midi_include == []
    assert cfg.midi.midi_exclude == []
    assert cfg.midi.midi_timing == MidiTiming.mido


def test_midi_config_can_be_flattened(mock_devices: None) -> None:
    cfg = Cfg(
        record_midi=False,
        midi_include=['Launchkey'],
        midi_exclude=['Network'],
        midi_timing='system',
    )

    assert not cfg.midi.record_midi
    assert cfg.midi.midi_include == ['Launchkey']
    assert cfg.midi.midi_exclude == ['Network']
    assert cfg.midi.midi_timing == MidiTiming.system


def test_cfg_reports_mutable_attributes(mock_devices: None) -> None:
    assert Cfg().mutable_attributes == {
        'audio.metadata',
        'device.profiles',
        'directory.output_directory',
        'directory.short_file_names',
        'keys.key_label',
        'recording.band_mode',
        'recording.channel_noise_floors',
        'recording.disk_alert_thresholds',
        'recording.disk_auto_switch',
        'recording.disk_poll_seconds',
        'recording.disk_removable_emergency',
        'recording.disk_removable_pause',
        'recording.disk_system_emergency',
        'recording.disk_system_pause',
        'recording.longest_file_time',
        'recording.minimum_free_space',
        'recording.noise_floor',
        'recording.preview_headroom',
        'recording.quiet_after_end',
        'recording.quiet_before_start',
        'recording.record_everything',
        'recording.shortest_file_time',
        'recording.stop_after_quiet',
        'recording.total_run_time',
    }


def test_cfg_rejects_immutable_attribute_changes(mock_devices: None) -> None:
    with pytest.raises(
        ValueError,
        match='Immutable configuration attribute: recording.memory_reserve_megabytes',
    ):
        Cfg().set_attr('recording.memory_reserve_megabytes', 4)


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


@pytest.mark.parametrize('field', ['disk_poll_seconds', 'memory_check_period'])
def test_buffer_times_must_be_positive(field: str, mock_devices: None) -> None:
    with pytest.raises(ValidationError, match='must be positive'):
        Cfg(**{field: 0})


@pytest.mark.parametrize('field', ['memory_reserve_megabytes', 'minimum_free_space'])
def test_memory_and_disk_reserves_must_not_be_negative(
    field: str, mock_devices: None
) -> None:
    with pytest.raises(ValidationError, match='must be non-negative'):
        Cfg(**{field: -1})


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
