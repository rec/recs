import re
from pathlib import Path

import pytest
from pydantic import ValidationError

from recs.edit.schema import canonical_toml, parse_edit
from recs.model.arrangement import ArrangementDocument
from recs.model.streams import AudioType


def test_documented_arrangement_separates_ports_from_destinations() -> None:
    path = Path(__file__).parents[2] / 'doc/arrangement-format.md'
    text = re.search(r'```toml\n(.*?)```', path.read_text(), re.DOTALL)
    assert text is not None
    document = parse_edit(text[1])
    assert document.body.outputs[0].id == document.destinations[0].port
    assert 'path' not in document.body.outputs[0].model_dump()
    assert parse_edit(canonical_toml(document)) == document
    assert ArrangementDocument.model_json_schema()['properties']['body']


def test_audio_ports_reject_other_quantities_and_duplicate_channels() -> None:
    with pytest.raises(ValidationError):
        AudioType.model_validate(
            {'timebase': 'audio', 'channels': ['left'], 'quantity': 'voltage'}
        )
    with pytest.raises(ValidationError, match='duplicate'):
        AudioType(timebase='audio', channels=['left', 'left'])
