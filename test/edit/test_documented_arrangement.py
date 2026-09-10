import re
from pathlib import Path

from ufor.arrangement import ArrangementScore
from ufor.codec import score_toml

from recs.edit.schema import parse_edit


def test_documented_arrangement_separates_ports_from_destinations() -> None:
    path = Path(__file__).parents[2] / 'doc/arrangement-format.md'
    text = re.search(r'```toml\n(.*?)```', path.read_text(), re.DOTALL)
    assert text is not None
    document = parse_edit(text[1])
    assert document.outputs[0].name == document.destinations[0].output
    assert 'path' not in document.outputs[0].model_dump()
    assert parse_edit(score_toml(document)) == document
    assert ArrangementScore.model_json_schema()['properties']['body']
