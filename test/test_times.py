import dataclasses as dc

import pytest

from recs.base import times


@pytest.mark.parametrize('db', (-10, 0, 3.1, 35, 123))
def test_db_to_amplitude(db):
    amp = times.db_to_amplitude(db)
    assert times.amplitude_to_db(amp) == pytest.approx(db)


@pytest.mark.parametrize('field', dc.fields(times.Times))
def test_negative_times(field):
    times.Times(**{field.name: 1})
    with pytest.raises(ValueError):
        times.Times(**{field.name: -1})
