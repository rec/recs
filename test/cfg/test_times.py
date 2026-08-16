import pytest

from recs.cfg import time_settings


@pytest.mark.parametrize('db', (-10, 0, 3.1, 35, 123, float('inf')))
def test_db_to_amplitude(db):
    amp = time_settings.db_to_amplitude(db)
    assert time_settings.amplitude_to_db(amp) == pytest.approx(db)


@pytest.mark.parametrize('field', time_settings.TimeSettings.model_fields)
def test_negative_times(field):
    time_settings.TimeSettings(**{field: 1})
    with pytest.raises(ValueError):
        time_settings.TimeSettings(**{field: -1})


def test_record_everything_is_not_scaled_to_samples() -> None:
    result = time_settings.TimeSettings(record_everything=True).scale(48_000)

    assert result.record_everything is True
