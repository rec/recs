import pytest
from pydantic import ValidationError

from recs.model.events import MidiEvent
from recs.model.sequence import Sequence


def test_sequence_extent_is_independent_of_event_count() -> None:
    sequence = Sequence(timebase='clock', end=48000, events=[])
    assert sequence.end == 48000


@pytest.mark.parametrize(
    'events',
    [
        [
            MidiEvent(tick=0, ordinal=1, data=[248]),
            MidiEvent(tick=0, ordinal=0, data=[248]),
        ],
        [
            MidiEvent(tick=0, ordinal=1, data=[248]),
            MidiEvent(tick=1, ordinal=1, data=[248]),
        ],
        [MidiEvent(tick=2, ordinal=0, data=[248])],
    ],
)
def test_sequence_rejects_ambiguous_order_or_out_of_range_events(
    events: list[MidiEvent],
) -> None:
    with pytest.raises(ValidationError):
        Sequence(timebase='clock', end=2, events=events)
