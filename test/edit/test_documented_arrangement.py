import re
from pathlib import Path

from ufor.arrangement import ArrangementDocument
from ufor.codec import document_toml

from recs.edit.schema import parse_edit


def test_documented_arrangement_separates_ports_from_destinations() -> None:
    path = Path(__file__).parents[2] / 'doc/arrangement-format.md'
    text = re.search(r'```toml\n(.*?)```', path.read_text(), re.DOTALL)
    assert text is not None
    document = parse_edit(text[1])
    assert document.ports[0].id == document.destinations[0].port
    assert 'path' not in document.ports[0].model_dump()
    assert parse_edit(document_toml(document)) == document
    assert ArrangementDocument.model_json_schema()['properties']['body']
