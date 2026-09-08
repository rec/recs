from pathlib import Path

import pytest
from pydantic import ValidationError
from ufor.arrangement import ArrangementDocument
from ufor.codec import document_toml

from recs.edit.schema import parse_edit, parse_partial_edit

COMPLETE_EDIT = """
format = "recs"
version = 1
kind = "arrangement"
id = "edit"
name = "Audio edit"
timebases = [{ id = "audio", rate = { numerator = 48000, denominator = 1 } }]
[body]
timebase = "audio"

[[body.sources]]
id = "voice-source"
record = "../recording.toml"
selector = { source = "X18", track = "1-2" }

[[body.tracks]]
id = "voice"
stream = { timebase = "audio", channels = ["channel-0", "channel-1"] }

[[body.buses]]
id = "master"
stream = { timebase = "audio", channels = ["channel-0", "channel-1"] }

[[body.clips]]
id = "opening"
source = "voice-source"
track = "voice"
source_start = 0
source_end = 48000
timeline_start = 0

[[body.routes]]
source = "voice"
destination = "master"
gain = 0.5

[[body.automation]]
target = { kind = "route", node = "voice", parameter = "gain", destination = "master" }
interpolation = "linear"
points = [
  { frame = 0, value = 0.0 },
  { frame = 48000, value = 0.5 },
]

[[body.outputs]]
id = "mix"
source = "master"

[[destinations]]
port = "mix"
path = "audio/mix.flac"
format = "flac"
subtype = "pcm_24"
"""


def test_complete_edit_round_trips_through_document_toml() -> None:
    edit = parse_edit(COMPLETE_EDIT)

    assert edit.body.sources[0].record == Path('../recording.toml')
    assert parse_edit(document_toml(edit)) == edit


def test_direct_file_source_round_trips() -> None:
    text = COMPLETE_EDIT.replace(
        'record = "../recording.toml"\n' 'selector = { source = "X18", track = "1-2" }',
        'file = "../take.wav"\nchannels = [0, 1]',
    )

    edit = parse_edit(text)

    assert edit.body.sources[0].file == Path('../take.wav')
    assert edit.body.sources[0].channels == [0, 1]
    assert parse_edit(document_toml(edit)) == edit


@pytest.mark.parametrize(
    'source',
    [
        '',
        'record = "record.jsonl"',
        'file = "take.wav"',
        'record = "record.jsonl"\n'
        'selector = { source = "device", track = "track" }\nfile = "take.wav"',
        'file = "take.wav"\nchannels = [1, 3]',
    ],
)
def test_source_requires_one_complete_location(source: str) -> None:
    text = COMPLETE_EDIT.replace(
        'record = "../recording.toml"\n' 'selector = { source = "X18", track = "1-2" }',
        source,
    )

    with pytest.raises(ValidationError):
        parse_edit(text)


def test_complete_edit_rejects_unknown_versions_and_fields() -> None:
    with pytest.raises(ValidationError):
        parse_edit(COMPLETE_EDIT.replace('version = 1', 'version = 2'))
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
    assert recipe.outputs[0].id is None
    assert recipe.command is not None
    assert recipe.command.help == 'Create a 24-bit extract'


def test_intervals_and_automation_points_are_ordered() -> None:
    with pytest.raises(ValidationError, match='source_end'):
        parse_edit(COMPLETE_EDIT.replace('source_end = 48000', 'source_end = 0'))
    with pytest.raises(ValidationError, match='strictly increasing'):
        parse_edit(COMPLETE_EDIT.replace('{ frame = 48000', '{ frame = 0'))


def test_edit_models_are_frozen() -> None:
    edit = parse_edit(COMPLETE_EDIT)

    with pytest.raises(ValidationError):
        edit.timebases[0].rate.numerator = 44_100
    assert isinstance(edit, ArrangementDocument)
