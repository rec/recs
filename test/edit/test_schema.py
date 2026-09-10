import pytest
from pydantic import ValidationError
from ufor.arrangement import ArrangementScore
from ufor.codec import score_toml

from recs.edit.schema import parse_edit, parse_partial_edit

COMPLETE_EDIT = """
format = "recs"
version = 3
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
name = "voice"

[body.tracks.stream]
timebase = "audio"
channels = ["channel-0", "channel-1"]

[[body.buses]]
name = "master"

[body.buses.stream]
timebase = "audio"
channels = ["channel-0", "channel-1"]

[[body.clips]]
name = "opening"
track = "voice"
source_start = 0
source_end = 48000
timeline_start = 0

[body.clips.source]
name = "voice-source"
output = "audio"

[[body.routes]]
source = "voice"
destination = "master"
gain = 0.5

[[body.automation]]
interpolation = "linear"

[[body.automation.points]]
frame = 0
value = 0.0

[[body.automation.points]]
frame = 48000
value = 0.5

[body.automation.target]
kind = "route"
name = "voice"
parameter = "gain"
destination = "master"

[[body.parts]]
name = "voice-source"

[body.parts.score]
path = "../recording.toml"

[[destinations]]
output = "mix"
path = "audio/mix.flac"
format = "flac"
subtype = "pcm_24"

[[outputs]]
name = "mix"

[outputs.stream]
timebase = "audio"
channels = ["channel-0", "channel-1"]

[outputs.binding]
bus = "master"
"""


def test_complete_edit_round_trips_through_score_toml() -> None:
    edit = parse_edit(COMPLETE_EDIT)

    assert edit.body.parts[0].score.path == '../recording.toml'
    assert parse_edit(score_toml(edit)) == edit


@pytest.mark.parametrize(
    'reference',
    [
        {},
        {'path': '/absolute.toml'},
        {'path': 'https://example.com/a.toml'},
        {'path': 'a.toml', 'sha256': 'bad'},
    ],
)
def test_definition_reference_requires_a_portable_path(
    reference: dict[str, object],
) -> None:
    data = parse_edit(COMPLETE_EDIT).model_dump()
    data['body']['parts'][0]['score'] = reference
    with pytest.raises(ValidationError):
        ArrangementScore.model_validate(data)


def test_complete_edit_rejects_unknown_versions_and_fields() -> None:
    with pytest.raises(ValidationError):
        parse_edit(COMPLETE_EDIT.replace('version = 3', 'version = 2'))
    with pytest.raises(ValidationError):
        parse_edit(COMPLETE_EDIT + '\nplugin = "danger.py"\n')


def test_partial_recipe_accepts_output_defaults() -> None:
    recipe = parse_partial_edit(
        """
extends = "clip"

[[outputs]]
format = "flac"
subtype = "pcm_24"
normalize = "none"

[_command]
help = "Create a 24-bit extract"
"""
    )

    assert recipe.extends == 'clip'
    assert recipe.outputs is not None
    assert recipe.outputs[0].name is None
    assert recipe.command is not None
    assert recipe.command.help == 'Create a 24-bit extract'


def test_intervals_and_automation_points_are_ordered() -> None:
    with pytest.raises(ValidationError, match='source_end'):
        parse_edit(COMPLETE_EDIT.replace('source_end = 48000', 'source_end = 0'))
    with pytest.raises(ValidationError, match='strictly increasing'):
        parse_edit(COMPLETE_EDIT.replace('frame = 48000', 'frame = 0'))


def test_edit_models_are_frozen() -> None:
    edit = parse_edit(COMPLETE_EDIT)

    with pytest.raises(ValidationError):
        edit.timebases[0].rate.numerator = 44_100
    assert isinstance(edit, ArrangementScore)
