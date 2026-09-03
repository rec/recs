from pathlib import Path

import pytest
import tyro
from pydantic import TypeAdapter, ValidationError

from recs.base import units
from recs.cfg.cfg import Cfg, Recording
from recs.cfg.cli import CliCfg
from recs.osc.config import Poll, Subscription
from recs.recsam import playback, processing, selection


@pytest.mark.parametrize(
    ('annotation', 'value', 'expected'),
    [
        (units.Seconds, '10ms', 0.01),
        (units.Seconds, '2 min', 120.0),
        (units.Seconds, '1:30', 90.0),
        (units.Seconds, '0.5', 0.5),
        (units.Seconds, 0.5, 0.5),
        (units.Milliseconds, '0.029s', 29),
        (units.Hertz, '2.4kHz', 2400.0),
        (units.Bytes, '2MB', 2_000_000),
        (units.Bytes, '2MiB', 2_097_152),
        (units.Bytes, '1KB', 1000),
        (units.Megabytes, '1GB', 1000),
    ],
)
def test_units_normalize_to_plain_numbers(
    annotation: object, value: object, expected: int | float
) -> None:
    result = TypeAdapter(annotation).validate_python(value)
    assert result == expected
    assert type(result) is type(expected)


@pytest.mark.parametrize(
    ('annotation', 'value'),
    [
        (units.Seconds, '3Hz'),
        (units.Hertz, '3ms'),
        (units.Bytes, '2s'),
        (units.Bytes, '90degree'),
        (units.Bytes, '2radian'),
        (units.Seconds, '3m'),
        (units.Milliseconds, '0.5ms'),
        (units.Bytes, '0.5byte'),
        (units.Megabytes, '1MiB'),
        (units.Seconds, 'junk'),
        (units.Seconds, 'ms'),
        (units.Seconds, '1 s/'),
        (units.Seconds, 'nan'),
        (units.Seconds, float('inf')),
        (units.Hertz, float('nan')),
        (units.Seconds, True),
    ],
)
def test_invalid_or_inexact_units_are_rejected(
    annotation: object, value: object
) -> None:
    with pytest.raises(ValidationError):
        TypeAdapter(annotation).validate_python(value)


def test_cli_and_api_use_the_same_numeric_config_values() -> None:
    parsed = tyro.cli(
        CliCfg,
        args=[
            '--quiet-before-start',
            '250ms',
            '--ui-refresh-rate',
            '20Hz',
            '--waveform-bucket-milliseconds',
            '0.02s',
            '--memory-reserve-megabytes',
            '1GB',
            '--minimum-free-space',
            '1GiB',
            '--disk-alert-thresholds',
            '1GiB',
        ],
    )
    assert parsed.recording.quiet_before_start == 0.25
    assert parsed.console.ui_refresh_rate == 20.0
    assert parsed.console.waveform_bucket_milliseconds == 20
    assert parsed.recording.memory_reserve_megabytes == 1000
    assert parsed.recording.minimum_free_space == 1_073_741_824
    assert parsed.recording.disk_alert_thresholds[-1] == '1073741824'
    updated = Cfg().set_attr('recording.quiet_before_start', '250ms')
    assert updated.get_attr('recording.quiet_before_start') == 0.25
    assert (
        Cfg.model_validate_json(updated.model_dump_json()).recording.quiet_before_start
        == 0.25
    )


def test_device_profiles_accept_units_and_keep_other_settings(tmp_path: Path) -> None:
    path = tmp_path / 'profiles.json'
    path.write_text(
        '{"Mic": {"quiet_after_end": "250ms", "minimum_free_space": "2MiB"}}'
    )
    cfg = Cfg(profiles=path, quiet_after_end=2)
    profiled = cfg.with_device_profile('Mic')
    assert profiled.recording.quiet_after_end == 0.25
    assert profiled.recording.minimum_free_space == 2_097_152
    assert cfg.recording.quiet_after_end == 2


@pytest.mark.parametrize(
    ('value', 'normalized'),
    [
        ('1GiB', '1073741824'),
        ('200MB', '200000000'),
        ('10m', '600s'),
        ('2 min', '120s'),
        ('0.25s', '0.25s'),
        ('10ms', '0.010s'),
        ('1e3', '1000'),
    ],
)
def test_disk_threshold_units_roundtrip(value: str, normalized: str) -> None:
    cfg = Recording(disk_alert_thresholds=[value])
    assert cfg.disk_alert_thresholds == [normalized]
    assert Recording.model_validate_json(
        cfg.model_dump_json()
    ).disk_alert_thresholds == [normalized]


@pytest.mark.parametrize(
    'value', ['-1s', 'nan', 'inf', '1e9999s', '1Hz', '1radian', '0.5B', 'unknown']
)
def test_invalid_disk_thresholds_fail_during_configuration(value: str) -> None:
    with pytest.raises(ValidationError):
        Recording(disk_alert_thresholds=[value])


def test_osc_periods_accept_units_without_changing_output_types() -> None:
    poll = Poll.model_validate({'path': '/status', 'period': '250ms'})
    subscription = Subscription.model_validate(
        {'path': '/remote', 'resubscribe_period': '1min'}
    )
    assert poll.period == 0.25
    assert subscription.resubscribe_period == 60.0
    assert poll.model_dump()['period'] == 0.25


def test_recsam_declarations_accept_units_but_keep_numeric_values() -> None:
    envelope = playback.Envelope.model_validate({'attack_seconds': '10ms'})
    mapping = playback.Mapping.model_validate(
        {
            'lowest_key': 0,
            'highest_key': 100,
            'reference_pitch_hz': '0.44kHz',
        }
    )
    lfo = playback.LFO.model_validate(
        {'id': 'slow', 'frequency_hz': '5Hz', 'delay_seconds': '20ms'}
    )
    band = processing.EqualizerBand.model_validate(
        {
            'id': 'tone',
            'frequency_hz': '2.4kHz',
            'gain_db': 3,
            'resonance': 1,
        }
    )
    choke = selection.Choke.model_validate(
        {'group': 'hats', 'mode': 'fade', 'fade_seconds': '5ms'}
    )
    assert envelope.attack_seconds == 0.01
    assert mapping.reference_pitch_hz == 440.0
    assert lfo.frequency_hz == 5.0
    assert lfo.delay_seconds == 0.02
    assert band.frequency_hz == 2400.0
    assert choke.fade_seconds == 0.005
