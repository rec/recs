import pytest
from pydantic import ValidationError

from recs.model.references import ParameterTarget, RecordSelector


def test_structured_selectors_preserve_punctuation() -> None:
    selector = RecordSelector(source='rack:one', track='mic:2', channel=0)
    assert RecordSelector.model_validate_json(selector.model_dump_json()) == selector


@pytest.mark.parametrize(
    'value',
    [
        {'kind': 'route', 'node': 'track'},
        {'kind': 'clip', 'node': 'clip', 'destination': 'master'},
    ],
)
def test_only_route_targets_require_destinations(value: dict[str, str]) -> None:
    with pytest.raises(ValidationError, match='destination'):
        ParameterTarget.model_validate(value)
