from pathlib import Path

import pytest

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
        (
            'target = { kind = "clip", node = "missing", parameter = "gain" }',
            'Unknown automation',
        ),
    ],
)
def test_graph_rejects_invalid_references(replacement: str, message: str) -> None:
    text = _edit()
    if replacement == 'channels = 2':
        text = text.replace(
            'channels = ["channel-0"]', 'channels = ["channel-0", "channel-1"]'
        )
    elif replacement == 'destination = "master"':
        text += """
[[body.routes]]
source = "master"
destination = "master"
"""
    else:
        text = text.replace(
            'target = { kind = "clip", node = "clip", parameter = "gain" }', replacement
        )

    with pytest.raises(ValueError, match=message):
        validate_graph(parse_edit(text), {'source': _source()})


def _source() -> ResolvedSource:
    return ResolvedSource(
        id='source',
        record=Path('recording.toml'),
        file=None,
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
format = "recs"
version = 1
kind = "arrangement"
id = "edit"
name = "Audio edit"
timebases = [{ id = "audio", rate = { numerator = 48000, denominator = 1 } }]
[body]
timebase = "audio"

[[body.sources]]
id = "source"
record = "recording.toml"
selector = { source = "device", track = "track" }

[[body.tracks]]
id = "track"
stream = { timebase = "audio", channels = ["channel-0"] }

[[body.buses]]
id = "master"
stream = { timebase = "audio", channels = ["channel-0"] }

[[body.clips]]
id = "clip"
source = "source"
track = "track"
source_start = 0
source_end = 48000
timeline_start = 0

[[body.routes]]
source = "track"
destination = "master"

[[body.automation]]
target = { kind = "clip", node = "clip", parameter = "gain" }
points = [{ frame = 0, value = 1.0 }]

[[body.outputs]]
id = "output"
source = "master"

[[destinations]]
port = "output"
path = "audio/output.wav"
format = "wav"
"""
