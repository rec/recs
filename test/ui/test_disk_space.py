import pytest

from recs.ui import disk_space


@pytest.mark.parametrize(
    ('value', 'bytes', 'seconds'),
    [
        ('50GB', 50_000_000_000, None),
        ('200MB', 200_000_000, None),
        ('10m', None, 600),
    ],
)
def test_parse_disk_threshold(
    value: str, bytes: int | None, seconds: float | None
) -> None:
    assert disk_space.parse_threshold(value) == disk_space.Threshold(bytes, seconds)


def test_time_threshold_uses_recent_write_rate() -> None:
    assert disk_space.threshold_bytes(['100MB', '10m'], 200_000) == 120_000_000


@pytest.mark.parametrize(
    ('value', 'formatted'),
    [(200_000_000, '200.0 M'), (5_300_000_000, '5.3 G')],
)
def test_free_space_uses_metric_units(value: int, formatted: str) -> None:
    assert disk_space.free_space(value) == formatted
