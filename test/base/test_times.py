import dataclasses as dc

import pytest

from recs.cfg import time_settings


@pytest.mark.parametrize('db', (-10, 0, 3.1, 35, 123))
def test_db_to_amplitude(db):
    amp = time_settings.db_to_amplitude(db)
    assert time_settings.amplitude_to_db(amp) == pytest.approx(db)


@pytest.mark.parametrize('field', dc.fields(time_settings.TimeSettings))
def test_negative_times(field):
    time_settings.TimeSettings(**{field.name: 1})
    with pytest.raises(ValueError):
        time_settings.TimeSettings(**{field.name: -1})
