from pathlib import Path

import pytest
from pydantic import ValidationError

from recs.edit.schema import EditSpec, canonical_toml, parse_edit, parse_partial_edit

COMPLETE_EDIT = """
schema_version = 1
sample_rate = 48000

[[sources]]
id = "voice-source"
record = "../session-record.jsonl"
channel = "X18:1-2"

[[tracks]]
id = "voice"
channels = 2

[[buses]]
id = "master"
channels = 2

[[clips]]
id = "opening"
source = "voice-source"
track = "voice"
source_start = 0
source_end = 48000
timeline_start = 0

[[routes]]
source = "voice"
destination = "master"
gain = 0.5

[[automation]]
target = "route:voice->master:gain"
interpolation = "linear"
points = [
  { frame = 0, value = 0.0 },
  { frame = 48000, value = 0.5 },
]

[[outputs]]
id = "mix"
source = "master"
path = "audio/mix.flac"
format = "flac"
subtype = "pcm_24"
"""


def test_complete_edit_round_trips_through_canonical_toml() -> None:
    edit = parse_edit(COMPLETE_EDIT)

    assert edit.sources[0].record == Path('../session-record.jsonl')
    assert parse_edit(canonical_toml(edit)) == edit


def test_complete_edit_rejects_unknown_versions_and_fields() -> None:
    with pytest.raises(ValidationError):
        parse_edit(COMPLETE_EDIT.replace('schema_version = 1', 'schema_version = 2'))
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
        edit.sample_rate = 44_100
    assert isinstance(edit, EditSpec)
