import pytest
from pydantic import ValidationError

from recs.model.time import Rate, TickRange, Timebase, convert_tick


@pytest.mark.parametrize(
    ('tick', 'source_rate', 'destination_rate', 'expected'),
    [
        (44100, 44100, 48000, 48000),
        (88200, 44100, 48000, 96000),
        (1, 2, 1, 0),
        (3, 2, 1, 2),
        (-3, 2, 1, -2),
    ],
)
def test_positions_convert_once_with_even_ties(
    tick: int, source_rate: int, destination_rate: int, expected: int
) -> None:
    source = Timebase(id='source', rate=Rate(numerator=source_rate))
    destination = Timebase(id='destination', rate=Rate(numerator=destination_rate))
    assert convert_tick(tick, source, destination) == expected


def test_rational_rates_preserve_exact_positions() -> None:
    source = Timebase(id='source', rate=Rate(numerator=30000, denominator=1001))
    destination = Timebase(id='destination', rate=Rate(numerator=48000))
    assert convert_tick(30000, source, destination) == 48048000


@pytest.mark.parametrize('value', [0, -1, True, 1.5])
def test_rates_reject_nonpositive_or_noninteger_values(value: object) -> None:
    with pytest.raises(ValidationError):
        Rate.model_validate({'numerator': value})


def test_ranges_are_nonempty_and_allow_preroll() -> None:
    assert TickRange(start=-1, end=0).start == -1
    with pytest.raises(ValidationError):
        TickRange(start=1, end=1)
