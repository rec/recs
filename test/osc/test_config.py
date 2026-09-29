import pytest
from pydantic import ValidationError

from recs.osc.config import Node


@pytest.mark.parametrize(
    'name', ['', 'x/y', 'x:y', 'x*', 'x?', 'CON', 'node.', 'node ']
)
def test_node_rejects_names_unsafe_for_portable_files(name: str) -> None:
    with pytest.raises(ValidationError, match='portable filename'):
        Node(name=name)


def test_node_accepts_portable_filename() -> None:
    assert Node(name='mixer-1').name == 'mixer-1'
