from pathlib import Path

import pytest
import tomlkit
from ufor.interface import Address

from recs.edit.graph import validate_graph
from recs.edit.record import AudioFragment, ResolvedSource
from recs.edit.schema import parse_edit


def test_graph_computes_routed_extent() -> None:
    edit = parse_edit(_edit())

    graph = validate_graph(edit, {Address(node='source', port='audio'): _source()})

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
        data = tomlkit.parse(text)
        data['body']['automation'][0]['target']['node'] = 'missing'
        text = tomlkit.dumps(data)

    with pytest.raises(ValueError, match=message):
        validate_graph(
            parse_edit(text), {Address(node='source', port='audio'): _source()}
        )


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
version = 2
kind = "arrangement"
id = "edit"
name = "Audio edit"

[[timebases]]
id = "audio"

[timebases.rate]
numerator = 48000
denominator = 1

[body]
timebase = "audio"

[[body.tracks]]
id = "track"

[body.tracks.stream]
timebase = "audio"
channels = ["channel-0"]

[[body.buses]]
id = "master"

[body.buses.stream]
timebase = "audio"
channels = ["channel-0"]

[[body.clips]]
id = "clip"
track = "track"
source_start = 0
source_end = 48000
timeline_start = 0

[body.clips.source]
node = "source"
port = "audio"

[[body.routes]]
source = "track"
destination = "master"

[[body.automation]]
[[body.automation.points]]
frame = 0
value = 1.0

[body.automation.target]
kind = "clip"
node = "clip"
parameter = "gain"

[[body.nodes]]
id = "source"

[body.nodes.definition]
path = "recording.toml"

[[destinations]]
port = "output"
path = "audio/output.wav"
format = "wav"

[[ports]]
id = "output"
direction = "output"

[ports.stream]
timebase = "audio"
channels = ["channel-0"]

[ports.binding]
bus = "master"
"""
