from pathlib import Path

import pytest
from ufor.interface import OutputSelection

from recs.edit.graph import validate_graph
from recs.edit.record import AudioFragment, ResolvedSource
from recs.edit.schema import parse_edit


def test_graph_computes_routed_extent() -> None:
    edit = parse_edit(_edit())

    graph = validate_graph(
        edit, {OutputSelection(part='source', output='audio'): _source()}
    )

    assert graph.bus_order == ['master']
    assert graph.output_extents['output'].start == 0
    assert graph.output_extents['output'].end == 48_000


@pytest.mark.parametrize(
    ('replacement', 'message'),
    [
        ('channels = 2', 'source width'),
        ('destination = "master"', 'Routing cycle'),
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
    with pytest.raises(ValueError, match=message):
        validate_graph(
            parse_edit(text),
            {OutputSelection(part='source', output='audio'): _source()},
        )


def _source() -> ResolvedSource:
    return ResolvedSource(
        name='source',
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
version = 4
kind = "arrangement"
name = "edit"
title = "Audio edit"
inputs = []

[[timebases]]
name = "audio"

[timebases.rate]
numerator = 48000
denominator = 1

[body]
timebase = "audio"

[[body.tracks]]
name = "track"

[body.tracks.stream]
timebase = "audio"
channels = ["channel-0"]

[[body.buses]]
name = "master"

[body.buses.stream]
timebase = "audio"
channels = ["channel-0"]

[[body.clips]]
name = "clip"
track = "track"
source_start = 0
source_end = 48000
timeline_start = 0

[body.clips.source]
part = "source"
output = "audio"

[[body.routes]]
source = "track"
destination = "master"

[[body.control_clips]]
name = "fade"
source_start = 0
source_end = 48000
timeline_start = 0

[body.control_clips.source]
part = "fade"
output = "control"

[[body.parts]]
name = "source"

[body.parts.score]
path = "recording.toml"

[[body.parts]]
name = "fade"

[body.parts.score]
format = "recs"
version = 4
kind = "automation"
name = "fade"
title = "Fade"

[[body.parts.score.timebases]]
name = "audio"

[body.parts.score.timebases.rate]
numerator = 48000
denominator = 1

[[body.parts.score.outputs]]
name = "control"
binding = { control = true }

[body.parts.score.outputs.stream]
family = "control"
timebase = "audio"
quantity = "gain"
unit = "ratio"
scope = "part"

[body.parts.score.body]
quantity = "gain"
unit = "ratio"
scope = "part"
default = 1.0

[body.parts.score.body.target]
kind = "clip"
name = "clip"

[[body.parts.score.body.curves]]
name = "gain"
unit = "ratio"
knots = [{ tick = 0, value = 1.0 }]

[[destinations]]
output = "output"
path = "audio/output.wav"
format = "wav"

[[outputs]]
name = "output"

[outputs.stream]
timebase = "audio"
channels = ["channel-0"]

[outputs.binding]
bus = "master"
"""
