from pathlib import Path

import pytest

from recs.base.errors import RecsError
from recs.edit.graph import validate_graph
from recs.edit.record import AudioFragment, ResolvedSource
from recs.edit.schema import parse_edit


def test_graph_computes_routed_extent() -> None:
    edit = parse_edit(_edit())

    graph = validate_graph(edit, {'source': _source()})

    assert graph.bus_order == ['master']
    assert graph.output_extents['output'].start == 0
    assert graph.output_extents['output'].end == 48_000


@pytest.mark.parametrize(
    ('replacement', 'message'),
    [
        ('channels = 2', 'source width'),
        ('destination = "master"', 'Routing cycle'),
        ('target = "clip:missing:gain"', 'Unknown automation'),
    ],
)
def test_graph_rejects_invalid_references(replacement: str, message: str) -> None:
    text = _edit()
    if replacement == 'channels = 2':
        text = text.replace('channels = 1', replacement, 1)
    elif replacement == 'destination = "master"':
        text += """
[[routes]]
source = "master"
destination = "master"
"""
    else:
        text = text.replace('target = "clip:clip:gain"', replacement)

    with pytest.raises(RecsError, match=message):
        validate_graph(parse_edit(text), {'source': _source()})


def _source() -> ResolvedSource:
    return ResolvedSource(
        id='source',
        record=Path('session-record.jsonl'),
        session_id='source-session',
        selector='device:track',
        channels=1,
        sample_rate=48_000,
        timeline_end=48_000,
        fragments=[
            AudioFragment(path=Path('audio.wav'), start=0, end=48_000, channels=1)
        ],
    )


def _edit() -> str:
    return """
schema_version = 1
sample_rate = 48000

[[sources]]
id = "source"
record = "session-record.jsonl"
channel = "device:track"

[[tracks]]
id = "track"
channels = 1

[[buses]]
id = "master"
channels = 1

[[clips]]
id = "clip"
source = "source"
track = "track"
source_start = 0
source_end = 48000
timeline_start = 0

[[routes]]
source = "track"
destination = "master"

[[automation]]
target = "clip:clip:gain"
points = [{ frame = 0, value = 1.0 }]

[[outputs]]
id = "output"
source = "master"
path = "audio/output.wav"
format = "wav"
"""
