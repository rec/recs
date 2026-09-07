import pytest
from pydantic import TypeAdapter, ValidationError

from recs.model.events import MidiEvent, OscEvent, StoredEvent


def test_raw_events_preserve_timestamp_order_and_payload() -> None:
    event = MidiEvent(tick=-1, ordinal=2, data=[144, 60, 100])
    adapter = TypeAdapter(StoredEvent)
    assert adapter.validate_json(adapter.dump_json(event)) == event


def test_packet_validation_rejects_invalid_storage() -> None:
    with pytest.raises(ValidationError, match='bytes'):
        MidiEvent(tick=0, ordinal=0, data=[256])
    with pytest.raises(ValidationError, match='base64'):
        OscEvent(tick=0, ordinal=0, direction='in', data_b64='!')
