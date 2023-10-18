import pytest

from recs.audio import times


@pytest.mark.parametrize('db', (-10, 0, 3.1, 35, 123))
def test_db_to_amplitude(db):
    amp = times.db_to_amplitude(db)
    assert times.amplitude_to_db(amp) == pytest.approx(db)
